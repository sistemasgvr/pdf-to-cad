using System;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.EditorInput;
using Autodesk.AutoCAD.Runtime;
using AcadApp = Autodesk.AutoCAD.ApplicationServices.Application;

// ============================================================================
//  CONFIGURACIÓN DE UNIDADES — fuerza el dibujo a IMPERIAL (pies).
//   · db.Insunits = Feet
//   · MEASUREMENT / MEASUREINIT = 0 (linetypes/hatch imperiales)
//   · Unidad AEC/Civil (DrawingSetupVariables.LinearUnit = Foot) — la que
//     rige cómo Civil 3D muestra las cotas de tuberías/estructuras.
//  El catálogo de partes (mm vs pulgadas) NO se puede fijar por una API
//  estable; se avisa para hacerlo una vez por la cinta si sigue en métrico.
// ============================================================================

namespace Civil3DBasico
{
    public class ComandosUnidades
    {
        [CommandMethod("USAR_IMPERIAL")]
        public void UsarImperial()
        {
            var doc = AcadApp.DocumentManager.MdiActiveDocument;
            if (doc == null) return;
            ForzarImperial(doc.Database, doc.Editor, true);
        }

        // Deja el dibujo en unidades imperiales. verbose = escribir en la línea de comandos.
        public static void ForzarImperial(Database db, Editor ed, bool verbose)
        {
            // 1) Unidades de inserción de AutoCAD
            try { db.Insunits = UnitsValue.Feet; } catch { }

            // 2) MEASUREMENT = 0 (imperial) para linetypes/patrones
            try { AcadApp.SetSystemVariable("MEASUREMENT", 0); } catch { }
            try { AcadApp.SetSystemVariable("MEASUREINIT", 0); } catch { }

            // 3) Unidad lineal AEC/Civil (la que ve Civil 3D para cotas)
            bool aecOk = false;
            try
            {
                ObjectId dsvId = Autodesk.Aec.ApplicationServices.DrawingSetupVariables.GetInstance(db, true);
                if (!dsvId.IsNull)
                {
                    using (Transaction tr = db.TransactionManager.StartTransaction())
                    {
                        var dsv = tr.GetObject(dsvId, OpenMode.ForWrite)
                                  as Autodesk.Aec.ApplicationServices.DrawingSetupVariables;
                        if (dsv != null)
                        {
                            dsv.LinearUnit = Autodesk.Aec.BuiltInUnit.Foot;
                            aecOk = true;
                        }
                        tr.Commit();
                    }
                }
            }
            catch (System.Exception ex) { if (verbose) ed.WriteMessage($"\n(No se pudo fijar la unidad AEC: {ex.Message})"); }

            if (verbose)
            {
                ed.WriteMessage($"\n✓ Dibujo en IMPERIAL: Insunits={db.Insunits}" + (aecOk ? " · unidad AEC = Foot." : "."));
                ed.WriteMessage("\n⚠ El catálogo de partes es aparte. Si las tuberías siguen saliendo en mm:" +
                                "\n   cinta Inicio → Red de tuberías ▼ → 'Establecer catálogo de red de tuberías' → US Imperial (una sola vez).");
            }
        }
    }
}
