using System;
using System.Linq;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using Civil3DBasico.Mcp.Aplicacion;
using Civil3DBasico.Mcp.Dominio;

// ============================================================================
//  ADAPTADOR de escritura: anotaciones (textos, MLEADER, cotas) y borrar guías.
//  Dentro de la transacción de `Aplicar` (un paso de U).
// ============================================================================

namespace Civil3DBasico.Mcp.Infraestructura
{
    internal sealed partial class Civil3DEditor
    {
        private static void Texto(Database db, Transaction tr, CambioTexto c)
        {
            foreach (EdicionTexto e in c.Ediciones)
            {
                var ent = (Entity)tr.GetObject(Existe(db, e.Handle), OpenMode.ForWrite);
                var v = new Vector3d(e.Dx, e.Dy, 0);
                switch (ent)
                {
                    case DBText t:
                        foreach (var (de, a) in e.Reemplazos) t.TextString = CambiosTexto.Limpio(Reemplazar(t.TextString, de, a));
                        if (e.Altura.HasValue) t.Height = e.Altura.Value;
                        if (v.Length > 1e-9) t.TransformBy(Matrix3d.Displacement(v));
                        break;
                    case MText mt:
                        EditarMText(mt, e);
                        if (v.Length > 1e-9) mt.TransformBy(Matrix3d.Displacement(v));
                        break;
                    case MLeader ml:
                        if (ml.MText is MText m2)
                        {
                            EditarMText(m2, e);
                            ml.MText = m2;
                        }
                        if (v.Length > 1e-9) ml.TextLocation = ml.TextLocation + v;
                        break;
                    case Dimension d:
                        foreach (var (de, a) in e.Reemplazos) d.DimensionText = CambiosTexto.Limpio(Reemplazar(string.IsNullOrEmpty(d.DimensionText) ? "<>" : d.DimensionText, de, a));
                        if (e.Altura.HasValue) d.Dimtxt = e.Altura.Value / Math.Max(d.Dimscale, 1e-9);
                        if (v.Length > 1e-9) { d.Dimtmove = 2; d.TextPosition = d.TextPosition + v; }
                        break;
                    default:
                        throw new ErrorUsuario($"{e.Handle} no es un texto ni una cota.");
                }
            }
        }

        /// <summary>MTEXT: el reemplazo va sobre su contenido con formato; si ahí no está (lo parte un código), sobre el
        /// texto plano (pierde el formato de ese texto).</summary>
        private static void EditarMText(MText mt, EdicionTexto e)
        {
            foreach (var (de, a) in e.Reemplazos)
            {
                if (mt.Contents.IndexOf(de, StringComparison.OrdinalIgnoreCase) >= 0) mt.Contents = Reemplazar(mt.Contents, de, a).Replace("  ", " ").Trim();
                else mt.Contents = CambiosTexto.Limpio(Reemplazar(mt.Text, de, a));
            }
            if (e.Altura.HasValue) mt.TextHeight = e.Altura.Value;
            if (e.Mascara.HasValue)
            {
                mt.BackgroundFill = e.Mascara.Value;
                if (e.Mascara.Value) { mt.UseBackgroundColor = true; mt.BackgroundScaleFactor = 1.25; }
            }
        }

        private static string Reemplazar(string s, string de, string a)
        {
            int i = (s ?? "").IndexOf(de ?? "", StringComparison.OrdinalIgnoreCase);
            return i < 0 || string.IsNullOrEmpty(de) ? s : s.Remove(i, de.Length).Insert(i, a ?? "");
        }

        private static void Borrar(Database db, Transaction tr, CambioBorrar c)
        {
            foreach (string h in c.Borrar.Distinct()) tr.GetObject(Existe(db, h), OpenMode.ForWrite).Erase();
        }

        private static void CotaCambio(Database db, Transaction tr, CambioCota c)
        {
            ObjectId estilo = ObjectId.Null;
            if (!string.IsNullOrWhiteSpace(c.Estilo))
            {
                var dst = (DimStyleTable)tr.GetObject(db.DimStyleTableId, OpenMode.ForRead);
                if (!dst.Has(c.Estilo)) throw new ErrorUsuario($"No existe el estilo de cota «{c.Estilo}» en el dibujo.");
                estilo = dst[c.Estilo];
            }
            if (c.Crear)
            {
                var p1 = new Point3d(c.X1, c.Y1, 0); var p2 = new Point3d(c.X2, c.Y2, 0);
                Vector3d u = (p2 - p1).GetNormal(), n = new Vector3d(-u.Y, u.X, 0);
                var d = new AlignedDimension(p1, p2, p1 + (p2 - p1) / 2 + n * c.Desplazamiento, "", estilo.IsNull ? db.Dimstyle : estilo);
                d.SetDatabaseDefaults(db);
                if (!estilo.IsNull) d.DimensionStyle = estilo;
                var ms = (BlockTableRecord)tr.GetObject(SymbolUtilityServices.GetBlockModelSpaceId(db), OpenMode.ForWrite);
                ms.AppendEntity(d);
                tr.AddNewlyCreatedDBObject(d, true);
                return;
            }
            foreach (string h in c.Cotas)
            {
                if (!(tr.GetObject(Existe(db, h), OpenMode.ForWrite) is Dimension d)) continue;
                if (!estilo.IsNull) d.DimensionStyle = estilo;
                double s = Math.Max(d.Dimscale, 1e-9);
                if (c.Decimales.HasValue) d.Dimdec = c.Decimales.Value;
                if (c.Flecha.HasValue) d.Dimasz = c.Flecha.Value / s;
                if (c.AlturaTexto.HasValue) d.Dimtxt = c.AlturaTexto.Value / s;
                if (c.TextoNuevo != null) d.DimensionText = c.TextoNuevo;
            }
        }
    }
}
