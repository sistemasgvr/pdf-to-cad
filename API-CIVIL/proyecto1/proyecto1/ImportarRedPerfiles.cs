using System;
using System.Collections.Generic;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.EditorInput;
using Autodesk.AutoCAD.Geometry;
using Exception = System.Exception;

// ============================================================================
//  IMPORTAR_RED paso 7 — perfiles longitudinales guardados en la app (2026-10-31)
//   · La app exporta un punto `PDFCAD_PERFIL` (NAME) por perfil guardado, sobre un
//     tramo de su recorrido. Aquí se crea cada uno con CREAR_PERFIL_RED sin preguntar
//     (`ComandosPerfil.CrearAutomatico`): misma red, mismo recorrido, mismos rótulos.
//   · Se colocan bajo el dibujo, uno debajo de otro, alineados a la izquierda.
// ============================================================================

namespace Civil3DBasico
{
    public partial class ComandosRedes
    {
        /// <summary>Separación vertical entre perfiles, en pulgadas de ploteo (× la escala del dibujo).</summary>
        private const double PERFIL_SEPARACION_IN = 14.0;

        private static void CrearPerfilesDeLaApp(Editor ed, Database db, List<(Point2d Semilla, Point2d? Fin, string Nombre)> perfiles)
        {
            if (perfiles == null || perfiles.Count == 0) return;
            ed.WriteMessage($"\n\n── 7. Perfiles longitudinales de la app: {perfiles.Count} ──");
            double s = 20;
            try
            {
                var u = Autodesk.Civil.ApplicationServices.CivilApplication.ActiveDocument.Settings.DrawingSettings.UnitZoneSettings;
                if (u.DrawingScale > 0 && u.DrawingScale <= 1000) s = u.DrawingScale;
            }
            catch { }
            double x0 = 0, y = 0;
            try
            {
                db.UpdateExt(true);
                x0 = db.Extmin.X;
                y = db.Extmin.Y - PERFIL_SEPARACION_IN * s;
            }
            catch { }
            int ok = 0;
            foreach (var (semilla, fin, nombre) in perfiles)
            {
                try
                {
                    if (ComandosPerfil.CrearAutomatico(semilla, fin, new Point3d(x0, y, 0), string.IsNullOrWhiteSpace(nombre) ? "?" : nombre))
                    {
                        ok++;
                        // el siguiente, debajo de todo lo que hay ahora (incluido este perfil)
                        try { db.UpdateExt(true); y = db.Extmin.Y - PERFIL_SEPARACION_IN * s; } catch { y -= PERFIL_SEPARACION_IN * s * 2; }
                    }
                }
                catch (Exception ex) { ed.WriteMessage($"\n  ✗ Perfil «{nombre}»: {ex.Message}"); }
            }
            ed.WriteMessage($"\n  ✔ {ok} de {perfiles.Count} perfil(es) creados.");
        }
    }
}
