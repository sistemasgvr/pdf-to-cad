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
                aStyle = EstiloEjeVisible(civilDoc, tr);
                aLabel = civilDoc.Styles.LabelSetStyles.AlignmentLabelSetStyles[0];
            }
            catch { return ObjectId.Null; }
            return CrearAlineamientoDesdePts(db, civilDoc, tr, pts, nombre, CapaEjeVisible(db, tr), aStyle, aLabel);
        }

        // Estilo de eje que SÍ dibuja la línea en planta (2026-10-06: con
        // AlignmentStyles[0] el eje salía invisible —solo sus etiquetas— cuando el
        // primer estilo del dibujo era uno sin visualización, p. ej. «_No Display»,
        // que por el «_» queda primero). Orden: el primero sin «_» con la línea
        // visible, luego cualquiera con la línea visible, y si no, el primero.
        internal static ObjectId EstiloEjeVisible(CivilDocument civilDoc, Transaction tr)
        {
            var col = civilDoc.Styles.AlignmentStyles;
            ObjectId conGuion = ObjectId.Null;
            foreach (ObjectId id in col)
            {
                try
                {
                    var st = tr.GetObject(id, OpenMode.ForRead) as Autodesk.Civil.DatabaseServices.Styles.AlignmentStyle;
                    if (st == null) continue;
                    if (!st.GetDisplayStylePlan(Autodesk.Civil.DatabaseServices.Styles.AlignmentDisplayStyleType.Line).Visible) continue;
                    if (!st.Name.StartsWith("_")) return id;
                    if (conGuion.IsNull) conGuion = id;
                }
                catch { }
            }
            return conGuion.IsNull ? col[0] : conGuion;
        }

        // Capa actual, salvo que esté apagada o congelada: entonces «0» (el eje no puede nacer invisible).
        internal static ObjectId CapaEjeVisible(Database db, Transaction tr)
        {
            try
            {
                var ltr = (LayerTableRecord)tr.GetObject(db.Clayer, OpenMode.ForRead);
                if (!ltr.IsOff && !ltr.IsFrozen) return db.Clayer;
                var lt = (LayerTable)tr.GetObject(db.LayerTableId, OpenMode.ForRead);
                return lt["0"];
            }
            catch { return db.Clayer; }
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
