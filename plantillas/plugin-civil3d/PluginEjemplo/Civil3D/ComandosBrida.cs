using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.EditorInput;
using Autodesk.AutoCAD.Geometry;
using Autodesk.AutoCAD.Runtime;
using AcApp = Autodesk.AutoCAD.ApplicationServices.Application;

// CIVIL 3D: el comando. Pide datos (ventana), calcula con la lógica PURA y solo aquí toca AutoCAD.
[assembly: CommandClass(typeof(Civil3DBasico.Ejemplo.ComandosBrida))]

namespace Civil3DBasico.Ejemplo
{
    public class ComandosBrida
    {
        /// <summary>Crea el sólido 3D de una brida (con agujeros) en el punto que indique el usuario.</summary>
        [CommandMethod("EJEMPLO_BRIDA")]
        public void CrearBrida()
        {
            Document doc = AcApp.DocumentManager.MdiActiveDocument;
            if (doc == null) return;
            Editor ed = doc.Editor;

            var ventana = new VentanaBrida();
            if (AcApp.ShowModalWindow(ventana) != true) return;

            ResultadoBrida r = CalculoBrida.Calcular(ventana.DiametroIn);
            if (!r.Valido)
            {
                ed.WriteMessage("\n" + r.Error);
                return;
            }

            PromptPointResult pp = ed.GetPoint("\nCentro de la brida: ");
            if (pp.Status != PromptStatus.OK) return;

            using (doc.LockDocument())
            using (Transaction tr = doc.Database.TransactionManager.StartTransaction())
            {
                var ms = (BlockTableRecord)tr.GetObject(SymbolUtilityServices.GetBlockModelSpaceId(doc.Database), OpenMode.ForWrite);
                Solid3d brida = Cilindro(CalculoBrida.APies(r.EspesorIn), CalculoBrida.APies(r.DiametroExteriorIn / 2.0), 0, 0);
                // Paso interior y agujeros de pernos: cilindros más altos que la brida, restados.
                double alto = CalculoBrida.APies(r.EspesorIn) * 1.5;
                Restar(brida, Cilindro(alto, CalculoBrida.APies(r.DiametroInteriorIn / 2.0), 0, 0));
                foreach (Punto2D p in r.Agujeros)
                    Restar(brida, Cilindro(alto, CalculoBrida.APies(r.DiametroAgujeroIn / 2.0),
                                           CalculoBrida.APies(p.X), CalculoBrida.APies(p.Y)));

                brida.TransformBy(Matrix3d.Displacement(pp.Value - Point3d.Origin));
                ms.AppendEntity(brida);
                tr.AddNewlyCreatedDBObject(brida, true);
                tr.Commit();
            }
            ed.WriteMessage("\nBrida de " + r.DiametroNominalIn + "\" creada (" + r.NumeroPernos + " pernos).");
        }

        static Solid3d Cilindro(double alto, double radio, double x, double y)
        {
            var s = new Solid3d();
            s.CreateFrustum(alto, radio, radio, radio);
            if (x != 0 || y != 0) s.TransformBy(Matrix3d.Displacement(new Vector3d(x, y, 0)));
            return s;
        }

        static void Restar(Solid3d a, Solid3d b)
        {
            a.BooleanOperation(BooleanOperationType.BoolSubtract, b);
            b.Dispose();
        }
    }
}
