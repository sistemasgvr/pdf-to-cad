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
//  comando (un paso de deshacer). Uno por CLASE de cambio (Dominio/Cambios.cs):
//  nada de código libre en AutoCAD. Mover, buzones y accesorios en
//  Civil3DEditorObra.cs.
// ============================================================================

namespace Civil3DBasico.Mcp.Infraestructura
{
    internal sealed partial class Civil3DEditor : IEditorDibujo
    {
        public void Aplicar(CambioPropuesto c) => HiloAutoCAD.Escribir(d =>
        {
            Database db = d.Database;
            Editor ed = d.Editor;
            if (c is CambioPerfil perfil) { CrearPerfil(db, ed, perfil); return; }
            using (Transaction tr = db.TransactionManager.StartTransaction())
            {
                switch (c)
                {
                    case CambioSimple s: Simple(db, tr, s); break;
                    case CambioMover mv: Mover(db, tr, mv, ed); break;
                    case CambioPendiente pe: Pendiente(db, tr, pe); break;
                    case CambioTamano ta:
                        foreach (TamanoNuevo t in ta.Tamanos)
                            Civil3DTamanos.Cambiar(tr, (Entity)tr.GetObject(Existe(db, t.Handle), OpenMode.ForWrite), t.Clave);
                        break;
                    case CambioBuzon bz: Buzon(db, tr, bz); break;
                    case CambioValvula va: Valvula(db, tr, va, ed); break;
                    case CambioQuitarAccesorio qa: QuitarAccesorio(db, tr, qa); break;
                    case CambioTexto tx: Texto(db, tr, tx); break;
                    case CambioBorrar bo: Borrar(db, tr, bo); break;
                    case CambioCota co: CotaCambio(db, tr, co); break;
                    case CambioConexionVertical cv:
                        ComandosRedes.McpConexionVertical(ed, db, tr, cv.TuberiaA, cv.TuberiaB, cv.X, cv.Y, cv.ZA, cv.ZB);
                        break;
                    default:
                        throw new ErrorUsuario($"Tipo de cambio no soportado: {c.Tipo}.");
                }
                tr.Commit();
            }
            ed.WriteMessage($"\n[IA] {c.Elemento}: {c.Tipo} {c.Antes} → {c.Despues}  (U para deshacer)");
        });

        private static void Simple(Database db, Transaction tr, CambioSimple c)
        {
            var ent = (Entity)tr.GetObject(Existe(db, c.Handle), OpenMode.ForWrite);
            switch (c.Tipo)
            {
                case TiposCambio.COTA_INICIO:
                case TiposCambio.COTA_FIN:
                    if (!(ent is CivilDB.Pipe p)) throw new ErrorUsuario("El elemento no es una tubería de gravedad.");
                    double z = double.Parse(c.Despues, System.Globalization.CultureInfo.InvariantCulture) + Civil3DLector.RadioInterior(p);
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
        }

        private static void Pendiente(Database db, Transaction tr, CambioPendiente c)
        {
            foreach (CotaNueva cz in c.Cotas)
            {
                if (!(tr.GetObject(Existe(db, cz.Handle), OpenMode.ForWrite) is CivilDB.Pipe tubo))
                    throw new ErrorUsuario($"{cz.Handle} no es una tubería de gravedad.");
                double r = Civil3DLector.RadioInterior(tubo);          // rasante → eje
                Point3d a0 = tubo.StartPoint, b0 = tubo.EndPoint;
                tubo.StartPoint = new Point3d(a0.X, a0.Y, cz.Ini + r);
                tubo.EndPoint = new Point3d(b0.X, b0.Y, cz.Fin + r);
            }
        }

        private static ObjectId Existe(Database db, string h)
        {
            ObjectId id = Ids.De(db, h);
            if (id.IsNull) throw new ErrorUsuario($"El elemento {h} ya no existe: volver a proponerlo.");
            return id;
        }

        /// <summary>Separación bajo el dibujo, en pulgadas de ploteo × la escala (como los perfiles de IMPORTAR_RED).</summary>
        private const double PERFIL_SEPARACION_IN = 14.0;

        /// <summary>CREAR_PERFIL_RED sin preguntar (`ComandosPerfil.CrearAutomatico`), debajo de todo el dibujo.
        /// Sin transacción propia: el perfil abre las suyas.</summary>
        private static void CrearPerfil(Database db, Editor ed, CambioPerfil c)
        {
            double s = 20;
            try
            {
                var u = Autodesk.Civil.ApplicationServices.CivilApplication.ActiveDocument.Settings.DrawingSettings.UnitZoneSettings;
                if (u.DrawingScale > 0 && u.DrawingScale <= 1000) s = u.DrawingScale;
            }
            catch { }
            double x0 = 0, y = 0;
            try { db.UpdateExt(true); x0 = db.Extmin.X; y = db.Extmin.Y - PERFIL_SEPARACION_IN * s; } catch { }
            Point2d? fin = c.FinX.HasValue && c.FinY.HasValue ? new Point2d(c.FinX.Value, c.FinY.Value) : (Point2d?)null;
            if (!ComandosPerfil.CrearAutomatico(new Point2d(c.SemillaX, c.SemillaY), fin, new Point3d(x0, y, 0), c.Elemento))
                throw new ErrorUsuario("No se pudo crear el perfil: el motivo está en la consola de Civil 3D.");
            ed.WriteMessage($"\n[IA] Perfil «{c.Elemento}» creado debajo del dibujo (U para deshacer).");
        }

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
