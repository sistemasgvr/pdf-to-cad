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
        // CREAR_PERFIL_RED — vista de perfil del EJE de una red de gravedad
        //   (+ perfil de terreno opcional). Requiere que la red tenga un
        //   ReferenceAlignmentId asociado (lo hace IMPORTAR_RED automáticamente).
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
                    ObjectIdCollection nets = civilDoc.GetPipeNetworkIds();
                    if (nets.Count == 0) { ed.WriteMessage("\nNo hay redes de tubería."); tr.Abort(); return; }

                    ObjectId netId = nets[0];
                    if (nets.Count > 1)
                    {
                        var nombres = new List<string>();
                        for (int i = 0; i < nets.Count; i++)
                        {
                            var n = tr.GetObject(nets[i], OpenMode.ForRead) as CivilDB.Network;
                            nombres.Add(n != null ? n.Name : $"(red {i + 1})");
                        }
                        ed.WriteMessage("\nRedes de tubería disponibles:");
                        for (int i = 0; i < nombres.Count; i++) ed.WriteMessage($"\n  {i + 1}. {nombres[i]}");
                        PromptIntegerOptions pio = new PromptIntegerOptions("\n¿Qué red? Número:")
                        { LowerLimit = 1, UpperLimit = nets.Count, DefaultValue = 1, UseDefaultValue = true };
                        PromptIntegerResult pir = ed.GetInteger(pio);
                        if (pir.Status != PromptStatus.OK) { tr.Abort(); return; }
                        netId = nets[pir.Value - 1];
                    }

                    CivilDB.Network net = (CivilDB.Network)tr.GetObject(netId, OpenMode.ForRead);
                    ObjectId alignId = net.ReferenceAlignmentId;
                    if (!alignId.IsValid || alignId.IsNull)
                    {
                        ed.WriteMessage("\nEsta red no tiene EJE asociado. Reimporta con IMPORTAR_RED (se crea el eje automáticamente).");
                        tr.Abort(); return;
                    }

                    ObjectId pStyle = civilDoc.Styles.ProfileStyles[0];
                    ObjectId pLabel = civilDoc.Styles.LabelSetStyles.ProfileLabelSetStyles[0];

                    // Perfil de terreno opcional
                    PromptKeywordOptions pkT = new PromptKeywordOptions("\n¿Dibujar el perfil del TERRENO desde una superficie? [Si/No] <No>:", "Si No");
                    pkT.AllowNone = true;
                    PromptResult rT = ed.GetKeywords(pkT);
                    if (rT.Status == PromptStatus.OK && rT.StringResult == "Si")
                    {
                        PromptEntityOptions peoS = new PromptEntityOptions("\nSeleccione la Superficie (TIN):");
                        peoS.SetRejectMessage("\nDebe ser una superficie TIN.");
                        peoS.AddAllowedClass(typeof(CivilDB.TinSurface), true);
                        PromptEntityResult perS = ed.GetEntity(peoS);
                        if (perS.Status == PromptStatus.OK)
                        {
                            try { CivilDB.Profile.CreateFromSurface("Terreno-Gravedad", alignId, perS.ObjectId, db.Clayer, pStyle, pLabel); }
                            catch (Exception ex) { ed.WriteMessage($"\n(No se pudo crear el perfil de terreno: {ex.Message})"); }
                        }
                    }

                    PromptPointResult pIns = ed.GetPoint("\nPunto de inserción de la vista de perfil:");
                    if (pIns.Status != PromptStatus.OK) { tr.Abort(); return; }
                    ObjectId pvId = CivilDB.ProfileView.Create(alignId, pIns.Value);

                    CivilDB.ProfileView pvW = tr.GetObject(pvId, OpenMode.ForWrite) as CivilDB.ProfileView;
                    bool rango = PerfilUtil.AjustarRango(pvW, alignId, tr);

                    tr.Commit();
                    ed.WriteMessage("\n✓ Vista de perfil creada para el eje de la red de gravedad." +
                                    (rango ? " Rango vertical ajustado (±5)." : ""));
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
