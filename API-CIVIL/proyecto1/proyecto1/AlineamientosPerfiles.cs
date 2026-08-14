using System;
using System.Collections.Generic;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.EditorInput;
using Autodesk.AutoCAD.Geometry;
using Autodesk.AutoCAD.Runtime;
using Autodesk.Civil.ApplicationServices;
using CivilDB = Autodesk.Civil.DatabaseServices;
using Exception = System.Exception;

// ============================================================================
//  ALINEAMIENTOS Y PERFILES DE REDES DE GRAVEDAD
//   · CrearAlineamientoDesdePts — helper compartido (usado por IMPORTAR_RED
//     y CREAR_RED_POLILINEA/COGO para asociar un eje a cada red).
//   · CREAR_PERFIL_RED — crea la vista de perfil del eje de la red de gravedad
//     (+ perfil de terreno opcional). Complementa a CREAR_PERFIL_PRESION.
// ============================================================================

namespace Civil3DBasico
{
    public class ComandosAlineamientos
    {
        // Crea un Alignment a lo largo de la planta (X-Y) de una lista de puntos.
        // Devuelve ObjectId.Null si algo falla (no bloquea flujos que lo llaman).
        public static ObjectId CrearAlineamientoDesdePts(Database db, CivilDocument civilDoc,
            Transaction tr, List<Point3d> pts, string nombre)
        {
            try
            {
                if (pts == null || pts.Count < 2) return ObjectId.Null;
                BlockTable bt = (BlockTable)tr.GetObject(db.BlockTableId, OpenMode.ForRead);
                BlockTableRecord ms = (BlockTableRecord)tr.GetObject(bt[BlockTableRecord.ModelSpace], OpenMode.ForWrite);
                Polyline pl = new Polyline();
                for (int i = 0; i < pts.Count; i++) pl.AddVertexAt(i, new Point2d(pts[i].X, pts[i].Y), 0, 0, 0);
                ms.AppendEntity(pl);
                tr.AddNewlyCreatedDBObject(pl, true);
                ObjectId aStyle = civilDoc.Styles.AlignmentStyles[0];
                ObjectId aLabel = civilDoc.Styles.LabelSetStyles.AlignmentLabelSetStyles[0];
                CivilDB.PolylineOptions plo = new CivilDB.PolylineOptions
                { PlineId = pl.ObjectId, AddCurvesBetweenTangents = false, EraseExistingEntities = true };
                return CivilDB.Alignment.Create(civilDoc, plo, nombre, ObjectId.Null, db.Clayer, aStyle, aLabel);
            }
            catch { return ObjectId.Null; }
        }

        // =====================================================================
        // CREAR_PERFIL_RED — perfil longitudinal profesional de una red de
        //   gravedad, dibujado 100% con entidades propias (no ProfileView
        //   nativo) para que el punto de inserción sea exactamente donde el
        //   usuario hace clic. Flujo: clic en una tubería/estructura de la red
        //   → clic en el punto de inserción → se dibuja. Sin más preguntas:
        //   el terreno se muestrea automáticamente si la red tiene superficie
        //   de referencia (net.ReferenceSurfaceId, la asigna IMPORTAR_RED).
        // =====================================================================
        [CommandMethod("CREAR_PERFIL_RED")]
        public void CrearPerfilRed()
        {
            Document doc = Application.DocumentManager.MdiActiveDocument;
            Editor ed = doc.Editor;
            Database db = doc.Database;
            CivilDocument civilDoc = CivilApplication.ActiveDocument;

            using (Transaction tr = db.TransactionManager.StartTransaction())
            {
                try
                {
                    // Selección de la red por CLIC en el dibujo (no por número escrito):
                    // así no importa el nombre/orden de la red, ni si hay una o varias.
                    PromptEntityOptions peoNet = new PromptEntityOptions(
                        "\nSeleccione una tubería o estructura de la red (clic en el dibujo):");
                    peoNet.SetRejectMessage("\nDebe seleccionar una tubería o estructura de una red de gravedad.");
                    peoNet.AddAllowedClass(typeof(CivilDB.Pipe), true);
                    peoNet.AddAllowedClass(typeof(CivilDB.Structure), true);
                    PromptEntityResult perNet = ed.GetEntity(peoNet);
                    if (perNet.Status != PromptStatus.OK) { tr.Abort(); return; }

                    // Cada lectura va en su propio try/catch: en redes con estructuras "raras"
                    // (p.ej. conduit/eléctricas) alguna propiedad puede tronar "Retrieve
                    // attribute failed" — no debe tumbar el comando completo por eso.
                    DBObject objSel = tr.GetObject(perNet.ObjectId, OpenMode.ForRead);
                    ObjectId netId = ObjectId.Null;
                    try
                    {
                        if (objSel is CivilDB.Pipe pipeSel) netId = pipeSel.NetworkId;
                        else if (objSel is CivilDB.Structure stSel) netId = stSel.NetworkId;
                    }
                    catch (Exception exNet) { ed.WriteMessage($"\nNo se pudo leer la red de esa entidad: {exNet.Message}"); tr.Abort(); return; }
                    if (netId.IsNull || !netId.IsValid) { ed.WriteMessage("\nEntidad no reconocida o sin red asociada."); tr.Abort(); return; }

                    CivilDB.Network net = tr.GetObject(netId, OpenMode.ForRead) as CivilDB.Network;
                    if (net == null) { ed.WriteMessage("\nNo se pudo obtener la red de esa entidad."); tr.Abort(); return; }

                    ObjectId alignId;
                    try { alignId = net.ReferenceAlignmentId; }
                    catch (Exception exAlign) { ed.WriteMessage($"\nNo se pudo leer el eje de la red: {exAlign.Message}"); tr.Abort(); return; }
                    if (!alignId.IsValid || alignId.IsNull)
                    {
                        ed.WriteMessage("\nEsta red no tiene EJE asociado. Reimporta con IMPORTAR_RED (se crea el eje automáticamente).");
                        tr.Abort(); return;
                    }
                    CivilDB.Alignment align = tr.GetObject(alignId, OpenMode.ForRead) as CivilDB.Alignment;

                    string nombreRed; try { nombreRed = net.Name; } catch { nombreRed = "Red"; }

                    // Topología de la red a lo largo de su eje (buzones ordenados por estación)
                    var (nodos, tramos) = PerfilLongitudinalDatos.Ordenar(net, align, tr);
                    if (nodos.Count < 2)
                    {
                        ed.WriteMessage("\nLa red tiene menos de 2 buzones proyectables sobre el eje: no se puede generar el perfil.");
                        tr.Abort(); return;
                    }

                    // La rasante inicial/final que el usuario fija es la de la TUBERÍA (no
                    // la del buzón): el primer/último buzón toman el invert exacto del
                    // primer/último tramo de tubería (misma fuente que Properties → Elevación
                    // de rasante), no el SumpElevation genérico del buzón.
                    if (tramos.Count > 0)
                    {
                        nodos[0].Invert = tramos[0].InvIni;
                        nodos[nodos.Count - 1].Invert = tramos[tramos.Count - 1].InvFin;
                    }

                    // Terreno real: automático si la red tiene superficie de referencia.
                    // Si no existe, queda vacío — nunca se inventa terreno.
                    var terreno = PerfilLongitudinalDatos.MuestrearTerreno(net, align, nodos, tr);

                    // Rasante de diseño como Profile nativo de Civil3D (dato de ingeniería
                    // real y consultable en Prospector; el dibujo del perfil NO depende de
                    // esto — es 100% propio, ver más abajo).
                    PerfilUtil.CrearPerfilRasante(civilDoc, db, alignId, nodos, nombreRed, tr);

                    PromptPointResult pIns = ed.GetPoint("\nPunto de inserción del perfil longitudinal:");
                    if (pIns.Status != PromptStatus.OK) { tr.Abort(); return; }
                    // ed.GetPoint devuelve el punto en el SCP activo; el dibujo se hace en WCS.
                    Point3d insWcs = pIns.Value.TransformBy(ed.CurrentUserCoordinateSystem);

                    PerfilLongitudinalDibujo.Generar(insWcs, net, nodos, tramos, terreno, db, tr);

                    tr.Commit();
                    ed.WriteMessage($"\n✓ Perfil longitudinal generado para '{nombreRed}' ({nodos.Count} buzones" +
                                     (terreno.Count > 0 ? ", con terreno" : ", sin superficie de referencia") + ").");
                }
                catch (Exception ex)
                {
                    ed.WriteMessage($"\nError: {ex.Message}");
                    tr.Abort();
                }
            }
        }
    }
}
