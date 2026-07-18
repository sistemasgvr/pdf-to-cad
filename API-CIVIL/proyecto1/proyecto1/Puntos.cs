using System;
using System.Collections.Generic;
using Autodesk.AutoCAD.ApplicationServices;
using AcadDB = Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.EditorInput;
using Autodesk.AutoCAD.Geometry;
using Autodesk.AutoCAD.Runtime;
using Autodesk.Civil.ApplicationServices;
using CivilDB = Autodesk.Civil.DatabaseServices; // alias: objetos de Civil 3D (CogoPoint...)
using Exception = System.Exception;

// ============================================================================
//  GUÍA RÁPIDA (detalle en README.md, sección 4)
//  - [CommandMethod("X")] = comando que escribes en Civil 3D.
//  - Patrón: doc/ed/db → Transaction → pedir datos (ed.Get...) → crear/leer → Commit.
//  - tr.GetObject(id, ForRead/ForWrite) = "abrir" un objeto por su ObjectId.
//  Alias de este archivo:
//    AcadDB  = Autodesk.AutoCAD.DatabaseServices   (objetos de AutoCAD: Polyline3d, BlockTable...)
//    CivilDB = Autodesk.Civil.DatabaseServices     (objetos de Civil 3D: CogoPoint...)
// ============================================================================

namespace Civil3DBasico
{
    /// <summary>
    /// Comandos relacionados con puntos / CogoPoints.
    /// </summary>
    public class ComandosPuntos
    {
        // UNIR_PUNTOS — une CogoPoints de Civil3D con una Polyline3d.
        // Flujo:
        //  1) Pregunta: Seleccionar manualmente o UsarTodos.
        //  2) Si seleccionar: toma la selección pero ignora lo que no sea CogoPoint.
        //  3) Pregunta orden: Numero o Descripcion.
        //  4) Crea una Polyline3d en ModelSpace uniendo los CogoPoints en ese orden.
        [CommandMethod("UNIR_PUNTOS")]
        public void UnirPuntosCommand()
        {
            Document doc = Application.DocumentManager.MdiActiveDocument;
            Editor ed = doc.Editor;
            CivilDocument civilDoc = CivilApplication.ActiveDocument;
            AcadDB.Database db = doc.Database;

            // Opción: Seleccionar manualmente o usar todos los CogoPoints
            PromptKeywordOptions optSel = new PromptKeywordOptions("\nSeleccionar CogoPoints manualmente o usar todos? [Seleccionar/UsarTodos] <Seleccionar>:");
            optSel.Keywords.Add("Seleccionar");
            optSel.Keywords.Add("UsarTodos");
            optSel.AllowNone = true;
            PromptResult optRes = ed.GetKeywords(optSel);
            if (optRes.Status != PromptStatus.OK && optRes.Status != PromptStatus.None) return;

            List<CivilDB.CogoPoint> lista = new List<CivilDB.CogoPoint>();

            using (AcadDB.Transaction tr = db.TransactionManager.StartTransaction())
            {
                // Construir conjunto de ObjectId de los CogoPoints existentes para validación rápida
                var setCogoIds = new HashSet<AcadDB.ObjectId>();
                CivilDB.CogoPointCollection allCogo = civilDoc.CogoPoints;
                foreach (AcadDB.ObjectId cid in allCogo)
                    setCogoIds.Add(cid);

                if (optRes.Status == PromptStatus.OK && optRes.StringResult == "UsarTodos")
                {
                    // Añadir todos los CogoPoints
                    foreach (AcadDB.ObjectId cid in allCogo)
                    {
                        var cp = tr.GetObject(cid, AcadDB.OpenMode.ForRead) as CivilDB.CogoPoint;
                        if (cp != null) lista.Add(cp);
                    }
                }
                else
                {
                    // Selección manual: sólo se aceptan entidades cuyo ObjectId sea de un CogoPoint.
                    PromptSelectionOptions selOpts = new PromptSelectionOptions();
                    selOpts.MessageForAdding = "\nSeleccione CogoPoints (si selecciona otras entidades serán ignoradas):";
                    PromptSelectionResult selRes = ed.GetSelection(selOpts);

                    if (selRes.Status != PromptStatus.OK)
                    {
                        ed.WriteMessage("\nSelección cancelada o vacía.");
                        return;
                    }

                    foreach (var soId in selRes.Value.GetObjectIds())
                    {
                        if (!setCogoIds.Contains(soId))
                        {
                            ed.WriteMessage($"\n(Info) Entidad {soId} ignorada: no es un CogoPoint.");
                            continue;
                        }

                        try
                        {
                            var cp = tr.GetObject(soId, AcadDB.OpenMode.ForRead) as CivilDB.CogoPoint;
                            if (cp != null) lista.Add(cp);
                        }
                        catch { /* ignorar posibles errores de lectura */ }
                    }
                }

                if (lista.Count == 0)
                {
                    ed.WriteMessage("\nNo se encontraron CogoPoints para unir.");
                    tr.Commit();
                    return;
                }

                // Preguntar orden
                PromptKeywordOptions ordOpts = new PromptKeywordOptions("\nOrdenar por: [Numero/Descripcion] <Numero>:");
                ordOpts.Keywords.Add("Numero");
                ordOpts.Keywords.Add("Descripcion");
                ordOpts.AllowNone = true;
                PromptResult ordRes = ed.GetKeywords(ordOpts);

                if (ordRes.Status == PromptStatus.OK && ordRes.StringResult == "Descripcion")
                {
                    lista.Sort((a, b) => string.Compare(a.RawDescription ?? string.Empty, b.RawDescription ?? string.Empty, StringComparison.OrdinalIgnoreCase));
                }
                else
                {
                    lista.Sort((a, b) => a.PointNumber.CompareTo(b.PointNumber));
                }

                // Crear Polyline3d en ModelSpace
                AcadDB.BlockTable bt = tr.GetObject(db.BlockTableId, AcadDB.OpenMode.ForRead) as AcadDB.BlockTable;
                AcadDB.BlockTableRecord ms = tr.GetObject(bt[AcadDB.BlockTableRecord.ModelSpace], AcadDB.OpenMode.ForWrite) as AcadDB.BlockTableRecord;

                AcadDB.Polyline3d pl3d = new AcadDB.Polyline3d(AcadDB.Poly3dType.SimplePoly, new Point3dCollection(), false);
                ms.AppendEntity(pl3d);
                tr.AddNewlyCreatedDBObject(pl3d, true);

                foreach (var cp in lista)
                {
                    AcadDB.PolylineVertex3d v = new AcadDB.PolylineVertex3d(new Point3d(cp.Easting, cp.Northing, cp.Elevation));
                    pl3d.AppendVertex(v);
                    tr.AddNewlyCreatedDBObject(v, true);
                }

                tr.Commit();

                ed.WriteMessage($"\n✓ Polilínea 3D creada uniendo {lista.Count} CogoPoints (orden: {(ordRes.Status == PromptStatus.OK && ordRes.StringResult == "Descripcion" ? "Descripcion" : "Numero")}).");
            }
        }
    }
}
