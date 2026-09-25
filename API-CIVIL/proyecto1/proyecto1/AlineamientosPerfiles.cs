using System;
using System.Collections.Generic;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using Autodesk.Civil.ApplicationServices;
using CivilDB = Autodesk.Civil.DatabaseServices;
using Exception = System.Exception;

// ============================================================================
//  ALINEAMIENTOS (EJES) DESDE PUNTOS
//   · CrearAlineamientoDesdePts — helper compartido: lo usa IMPORTAR_RED para
//     asociar un eje a cada red y el perfil (PerfilEje, DISENO.md D.2) para su
//     eje propio en la capa PDFCAD_PERFIL_EJE.
//   · El comando CREAR_PERFIL_RED vive ahora en PerfilComando.cs.
// ============================================================================

namespace Civil3DBasico
{
    public class ComandosAlineamientos
    {
        // Crea un Alignment a lo largo de la planta (X-Y) de una lista de puntos
        // RECTOS (todos los bulges en 0).
        // Devuelve ObjectId.Null si algo falla (no bloquea flujos que lo llaman).
        public static ObjectId CrearAlineamientoDesdePts(Database db, CivilDocument civilDoc,
            Transaction tr, List<Point3d> pts, string nombre)
        {
            if (pts == null) return ObjectId.Null;
            var conBulge = new List<ComandosRedes.TrazaPt>(pts.Count);
            foreach (var p in pts) conBulge.Add(new ComandosRedes.TrazaPt(p));
            return CrearAlineamientoDesdePts(db, civilDoc, tr, conBulge, nombre);
        }

        // Igual que la anterior, pero cada punto lleva el BULGE del segmento que
        // empieza en él: así el eje describe los mismos ARCOS que las tuberías
        // curvas (esquinas redondeadas de bancoducto) en vez de cortarlos con la
        // cuerda. Es el equivalente al "Free curve fillet" de Civil 3D, aplicado
        // desde la geometría en vez de a mano. Capa actual y primeros estilos
        // (comportamiento de IMPORTAR_RED).
        public static ObjectId CrearAlineamientoDesdePts(Database db, CivilDocument civilDoc,
            Transaction tr, List<ComandosRedes.TrazaPt> pts, string nombre)
        {
            ObjectId aStyle, aLabel;
            try
            {
                aStyle = civilDoc.Styles.AlignmentStyles[0];
                aLabel = civilDoc.Styles.LabelSetStyles.AlignmentLabelSetStyles[0];
            }
            catch { return ObjectId.Null; }
            return CrearAlineamientoDesdePts(db, civilDoc, tr, pts, nombre, db.Clayer, aStyle, aLabel);
        }

        // Sobrecarga con capa, estilo y juego de etiquetas explícitos (DISENO.md D.2).
        // Si Alignment.Create falla, la polilínea auxiliar se BORRA (antes quedaba
        // huérfana en ModelSpace): por eso se declara fuera del try.
        public static ObjectId CrearAlineamientoDesdePts(Database db, CivilDocument civilDoc, Transaction tr,
            List<ComandosRedes.TrazaPt> pts, string nombre, ObjectId layerId, ObjectId styleId, ObjectId labelSetId)
        {
            if (pts == null || pts.Count < 2) return ObjectId.Null;
            Polyline pl = null;                                   // declarada FUERA del try (arreglo del huérfano)
            try
            {
                var btr = (BlockTableRecord)tr.GetObject(SymbolUtilityServices.GetBlockModelSpaceId(db), OpenMode.ForWrite);
                pl = new Polyline();
                for (int i = 0; i < pts.Count; i++)
                    pl.AddVertexAt(i, new Point2d(pts[i].P.X, pts[i].P.Y), pts[i].Bulge, 0, 0);
                btr.AppendEntity(pl);
                tr.AddNewlyCreatedDBObject(pl, true);
                // AddCurvesBetweenTangents=false NO borra los arcos que la polilínea
                // ya trae (esos pasan a ser entidades AlignmentArc); solo evita que
                // Civil 3D INVENTE fillets donde no los pedimos.
                var opt = new CivilDB.PolylineOptions
                { PlineId = pl.ObjectId, AddCurvesBetweenTangents = false, EraseExistingEntities = true };
                return CivilDB.Alignment.Create(civilDoc, opt, nombre, ObjectId.Null, layerId, styleId, labelSetId);
            }
            catch (Exception)
            {
                try
                {
                    if (pl != null && !pl.IsErased)
                    {
                        if (!pl.IsWriteEnabled) pl.UpgradeOpen();
                        pl.Erase();
                    }
                }
                catch { }
                return ObjectId.Null;
            }
        }
    }
}
