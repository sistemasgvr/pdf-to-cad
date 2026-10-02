using System;
using System.Collections.Generic;
using System.Linq;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.EditorInput;
using Autodesk.AutoCAD.Geometry;
using Autodesk.AutoCAD.Runtime;
using Autodesk.Civil.ApplicationServices;
using Autodesk.Civil.Settings;
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

        private sealed class Medida { public double W, H, Ax, Ay; public Extents3d E; public bool Ok; }

        private static Medida Medir(Transaction tr, ObjectId id, string que)
        {
            var m = new Medida();
            try
            {
                var l = (CivilDB.Label)tr.GetObject(id, OpenMode.ForRead);
                m.E = l.GeometricExtents; m.Ok = true;
                m.W = m.E.MaxPoint.X - m.E.MinPoint.X; m.H = m.E.MaxPoint.Y - m.E.MinPoint.Y;
                m.Ax = l.AnchorInfo.Location.X; m.Ay = l.AnchorInfo.Location.Y;
                PerfilLog.Log("PRUEBA", $"{que}: ext=({m.E.MinPoint.X:0.###},{m.E.MinPoint.Y:0.###})-({m.E.MaxPoint.X:0.###},{m.E.MaxPoint.Y:0.###}) " +
                                        $"W={m.W:0.###} H={m.H:0.###} ancla=({m.Ax:0.###},{m.Ay:0.###}) loc={l.LabelLocation} dragged={l.Dragged} rot={l.RotationAngle:0.###}");
            }
            catch (Exception ex) { PerfilLog.Error("PRUEBA", que, ex); }
            return m;
        }

        /// <summary>Prueba de humo J: pide una ProfileView, crea, mide, arrastra y vuelve a medir dos etiquetas.</summary>
        [CommandMethod("PDFCAD_PERFIL_PRUEBA")]
        public void PruebaPerfil()
        {
            Document doc = Application.DocumentManager.MdiActiveDocument;
            if (doc == null) return;
            var ed = doc.Editor; var db = doc.Database; var civ = CivilApplication.ActiveDocument;
            PerfilLog.Iniciar();
            var peo = new PromptEntityOptions("\nSeleccione una vista de perfil existente:");
            peo.SetRejectMessage("\nDebe ser una vista de perfil.");
            peo.AddAllowedClass(typeof(CivilDB.ProfileView), true);
            var pr = ed.GetEntity(peo);
            if (pr.Status != PromptStatus.OK) return;
            double s = 20;
            bool metros = false;
            try { var u = civ.Settings.DrawingSettings.UnitZoneSettings; if (u.DrawingScale > 0 && u.DrawingScale <= 1000) s = u.DrawingScale; metros = u.DrawingUnits == DrawingUnitType.Meters; } catch { }
            var lineas = TEXTO_PRUEBA.Split(new[] { "\\P" }, StringSplitOptions.None).ToList();
            ObjectId sup = ObjectId.Null, inf = ObjectId.Null;
            double factor = PerfilEstilos.FACTOR_PL_PIES;
            try
            {
                using (Transaction tr = db.TransactionManager.StartTransaction())
                {
                    factor = PerfilEstilos.FactorPlInicial(tr, civ, metros, out string origen);
                    double v = PerfilDiseno.ElegirV(s);
                    var est = PerfilEstilos.Asegurar(tr, db, civ, s, v, PerfilDiseno.ElegirIntervalos(s, v), factor, factor);
                    PerfilEstilosEtiquetas.Diagnostico(tr, db, civ, factor, origen);
                    var pv = (CivilDB.ProfileView)tr.GetObject(pr.ObjectId, OpenMode.ForRead);
                    double e0 = pv.StationStart, e1 = pv.StationEnd, z = (pv.ElevationMin + pv.ElevationMax) / 2.0;
                    sup = PerfilEtiquetas.CrearStationElevation(tr, pr.ObjectId, est.CalloutSup, est.SinMarcador, e0 + 0.3 * (e1 - e0), z, lineas);
                    inf = PerfilEtiquetas.CrearStationElevation(tr, pr.ObjectId, est.CalloutInf, est.SinMarcador, e0 + 0.6 * (e1 - e0), z, lineas);
                    tr.Commit();
                }
                ComandosPerfil.Flush(doc);
                Medida m1s, m1i;
                using (Transaction tr = db.TransactionManager.StartTransaction())
                {
                    m1s = Medir(tr, sup, "sup antes"); m1i = Medir(tr, inf, "inf antes");
                    foreach (var (id, dy) in new[] { (sup, 1.5 * s), (inf, -1.5 * s) })
                    {
                        if (id.IsNull) continue;
                        var l = (CivilDB.Label)tr.GetObject(id, OpenMode.ForWrite);
                        l.LabelLocation = l.LabelLocation + new Vector3d(0, dy, 0);
                        PerfilEtiquetas.Leaders(l, true, true);
                    }
                    tr.Commit();
                }
                ComandosPerfil.Flush(doc);
                Medida m2s, m2i;
                using (Transaction tr = db.TransactionManager.StartTransaction())
                {
                    m2s = Medir(tr, sup, "sup después"); m2i = Medir(tr, inf, "inf después");
                    tr.Commit();
                }
                // I-1: el ancho de un bloque vertical de 3 líneas debe medir 0.52" de ploteo
                double pred = PerfilDiseno.AnchoBloqueVertical(3);
                double rW = m1s.Ok && m1s.W > 1e-9 ? (m1s.W / s) / pred : 1.0;
                double sugerido = factor / rW;
                bool vertical = m2s.Ok && m2i.Ok && m2s.H > m2s.W && m2i.H > m2i.W;
                string Eng(Medida m) { if (!m.Ok) return "?"; double yc = (m.E.MinPoint.Y + m.E.MaxPoint.Y) / 2.0; return m.Ay < yc ? "abajo" : "arriba"; }
                string texto = $"\n✓ PDFCAD_PERFIL_PRUEBA: ancho medido {rW:0.###}× lo previsto → FactorPl sugerido {sugerido:G4} (actual {factor:G4})." +
                               $"\n· Texto vertical tras el arrastre: {(vertical ? "OK" : "NO")}." +
                               $"\n· Leader de la franja superior engancha {Eng(m2s)} (esperado: abajo); inferior {Eng(m2i)} (esperado: arriba)." +
                               "\n· Revise a la vista que «45%%d» se vea como «45°» y que haya tres líneas." +
                               "\n· Detalle en " + PerfilLog.Ruta;
                PerfilLog.Log("PRUEBA", texto.Replace("\n", " "));
                ed.WriteMessage(texto);
            }
            catch (Exception ex)
            {
                PerfilLog.Error("PRUEBA", "prueba de humo", ex);
                ed.WriteMessage("\n✗ PDFCAD_PERFIL_PRUEBA: " + ex.Message + " (detalle en " + PerfilLog.Ruta + ")");
            }
        }
    }
}
