using System;
using System.Collections.Generic;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.EditorInput;
using Autodesk.AutoCAD.Runtime;
using Autodesk.Civil.ApplicationServices;
using CivilDB = Autodesk.Civil.DatabaseServices; // alias: objetos de Civil 3D (CogoPoint, Alignment, TinSurface...)
using Exception = System.Exception;

// ============================================================================
//  Utilidad de diagnóstico del dibujo (DIAG_ENTIDADES).
//  Los comandos manuales de creación (puntos/CogoPoints/alineamiento/superficie
//  y utilidades de curvas de nivel) se retiraron: el flujo real es IMPORTAR_RED.
// ============================================================================

namespace Civil3DBasico
{
    /// <summary>
    /// Diagnóstico del dibujo: reporta qué entidades hay y si las polilíneas
    /// tienen elevación 3D real (útil antes de intentar armar una superficie).
    /// </summary>
    public class ComandosCivilReal
    {
        // =====================================================================
        // DIAGNÓSTICO: qué hay en el dibujo y si sirve para crear superficie.
        // Reporta tipos de entidad, capas y — lo más importante — el RANGO DE Z
        // de los vértices de las polilíneas. Si Zmin ≈ Zmax ≈ 0, las curvas son
        // planas (cota solo como texto) y NO sirven directamente.
        // =====================================================================
        [CommandMethod("DIAG_ENTIDADES")]
        public void DiagnosticoEntidades()
        {
            Document doc = Application.DocumentManager.MdiActiveDocument;
            Editor ed = doc.Editor;
            Database db = doc.Database;
            CivilDocument civilDoc = CivilApplication.ActiveDocument;

            int nLw = 0, nP2 = 0, nP3 = 0, nLine = 0, nPoint = 0, nOtros = 0;
            double zMin = double.MaxValue, zMax = double.MinValue;
            int vertsConZ = 0, vertsTotal = 0;
            var capas = new HashSet<string>();

            void Track(double z) { vertsTotal++; if (Math.Abs(z) > 1e-6) vertsConZ++; if (z < zMin) zMin = z; if (z > zMax) zMax = z; }

            using (Transaction tr = db.TransactionManager.StartTransaction())
            {
                BlockTable bt = (BlockTable)tr.GetObject(db.BlockTableId, OpenMode.ForRead);
                BlockTableRecord ms = (BlockTableRecord)tr.GetObject(bt[BlockTableRecord.ModelSpace], OpenMode.ForRead);

                foreach (ObjectId id in ms)
                {
                    DBObject obj = tr.GetObject(id, OpenMode.ForRead);
                    if (obj is Polyline lw)
                    {
                        nLw++; capas.Add(lw.Layer);
                        for (int i = 0; i < lw.NumberOfVertices; i++) Track(lw.GetPoint3dAt(i).Z);
                    }
                    else if (obj is Polyline3d p3)
                    {
                        nP3++; capas.Add(p3.Layer);
                        foreach (ObjectId vId in p3)
                        {
                            PolylineVertex3d v = tr.GetObject(vId, OpenMode.ForRead) as PolylineVertex3d;
                            if (v != null) Track(v.Position.Z);
                        }
                    }
                    else if (obj is Polyline2d p2)
                    {
                        nP2++; capas.Add(p2.Layer);
                        foreach (ObjectId vId in p2)
                        {
                            Vertex2d v = tr.GetObject(vId, OpenMode.ForRead) as Vertex2d;
                            if (v != null) Track(v.Position.Z);
                        }
                    }
                    else if (obj is Line) nLine++;
                    else if (obj is DBPoint) nPoint++;
                    else nOtros++;
                }
                tr.Commit();
            }

            int nCogo = 0;
            try { nCogo = (int)civilDoc.CogoPoints.Count; } catch { }

            ed.WriteMessage("\n================ DIAGNÓSTICO DEL DIBUJO ================");
            ed.WriteMessage($"\n  CogoPoints (Civil 3D): {nCogo}");
            ed.WriteMessage($"\n  Polilíneas 2D ligeras (LWPOLYLINE): {nLw}");
            ed.WriteMessage($"\n  Polilíneas 2D pesadas (POLYLINE 2D): {nP2}");
            ed.WriteMessage($"\n  Polilíneas 3D (POLYLINE 3D): {nP3}");
            ed.WriteMessage($"\n  Líneas / Puntos AutoCAD / Otros: {nLine} / {nPoint} / {nOtros}");
            ed.WriteMessage($"\n  Capas de polilíneas: {(capas.Count > 0 ? string.Join(", ", capas) : "(ninguna)")}");
            if (vertsTotal > 0)
            {
                ed.WriteMessage($"\n  Vértices de polilíneas: {vertsTotal}  (con Z≠0: {vertsConZ})");
                ed.WriteMessage($"\n  Rango de elevación Z: {zMin:F3}  a  {zMax:F3}");
                bool planas = (zMax - zMin) < 0.001;
                ed.WriteMessage(planas
                    ? "\n  >>> ⚠ Las polilíneas son PLANAS (sin Z). NO sirven directas para superficie; hay que asignarles elevación primero."
                    : "\n  >>> ✓ Las polilíneas TIENEN elevación 3D.");
            }
            else ed.WriteMessage("\n  No se encontraron polilíneas en ModelSpace.");
            ed.WriteMessage("\n========================================================");
        }
    }
}
