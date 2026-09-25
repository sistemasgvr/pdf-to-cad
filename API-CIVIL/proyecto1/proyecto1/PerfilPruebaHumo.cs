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
//  PDFCAD_PERFIL_PRUEBA — prueba de humo en Civil 3D (DISENO.md J)
//   · Sobre una ProfileView existente crea dos etiquetas Callout Sup/Inf con un
//     texto de 3 líneas, las mide, las arrastra ±1.5"·S con leader y vuelve a
//     medir: valida I-1 (FactorPl), I-2 (vertical tras arrastre), I-5 (\P y %%d)
//     e I-19 (lado de enganche del leader). Todo al log y un mensaje final.
// ============================================================================

namespace Civil3DBasico
{
    public class ComandosPerfilPrueba
    {
        /// <summary>Texto de prueba de J-2 (3 líneas unidas con \P).</summary>
        internal const string TEXTO_PRUEBA = "PIPE STA 1+00.00\\P8\" X 45%%d BEND\\PTOP ELEV 745.43'";

        /// <summary>Prueba de humo J: pide una ProfileView, crea, mide, arrastra y vuelve a medir dos etiquetas.</summary>
        [CommandMethod("PDFCAD_PERFIL_PRUEBA")]
        public void PruebaPerfil()
        {
            Document doc = Application.DocumentManager.MdiActiveDocument;
            if (doc == null) return;
            doc.Editor.WriteMessage("\n⚠ PDFCAD_PERFIL_PRUEBA: en construcción.");
        }
    }
}
