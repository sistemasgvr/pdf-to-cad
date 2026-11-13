using System;
using System.Collections.Generic;
using System.IO;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.EditorInput;
using Autodesk.Civil.ApplicationServices;
using CivilDB = Autodesk.Civil.DatabaseServices;
using Exception = System.Exception;

// ============================================================================
//  IMPORTAR_RED paso 6b — superficies (terreno) de la app (2026-11-11, 2.1.0)
//   · La app escribe un LandXML (TIN) por superficie y un punto PDFCAD_SUPERFICIE
//     en el DXF (capa PDFCAD_SUPERFICIES) con lo esperado. Aquí se crea cada una con
//     TinSurface.CreateFromLandXML y se VERIFICA contra el XDATA (puntos, triángulos,
//     cotas, recuadro, muestras con FindElevationAtXY).
//   · Exactitud: los números del LandXML ya están en el sistema del dibujo. Se importa
//     una COPIA con el <Units> igual al del dibujo (y sin <CoordinateSystem>), y con
//     traslación, giro y «pie topográfico → internacional» apagados mientras dura la
//     importación (se reponen después): Civil 3D no escala ni mueve nada.
//   · Antes de los perfiles (paso 7): el perfil toma la primera TIN del dibujo como terreno.
//   · Nunca aborta la importación de redes: todo problema se avisa y se sigue.
// ============================================================================

namespace Civil3DBasico
{
    public partial class ComandosRedes
    {
        private const string CAPA_SUPERFICIE = "C-TOPO-SUPERFICIE";

        private static void CrearSuperficiesDeLaApp(Editor ed, Document doc, Database db, List<SuperficiesNucleo.Registro> sups)
        {
            if (sups == null || sups.Count == 0) return;
            ed.WriteMessage($"\n\n── 6b. Superficies (terreno) de la app: {sups.Count} ──");
            var carpetas = new List<string>();
            foreach (string f in new[] { doc?.Name, db.Filename, db.OriginalFileName })
            {
                try
                {
                    if (string.IsNullOrWhiteSpace(f) || !Path.IsPathRooted(f)) continue;
                    string c = Path.GetDirectoryName(f);
                    if (!string.IsNullOrEmpty(c) && !carpetas.Contains(c)) carpetas.Add(c);
                }
                catch { }
            }
            int creadas = 0;
            foreach (var reg in sups)
            {
                try { if (CrearSuperficie(ed, db, reg, carpetas)) creadas++; }
                catch (Exception ex) { ed.WriteMessage($"\n  ✗ Superficie «{reg.Nombre}»: {ex.Message}"); }
            }
            ed.WriteMessage($"\n  · {creadas} de {sups.Count} superficie(s) creadas.");
        }

        /// <summary>True si se creó una superficie nueva.</summary>
        private static bool CrearSuperficie(Editor ed, Database db, SuperficiesNucleo.Registro reg, List<string> carpetas)
        {
            string nombre = string.IsNullOrWhiteSpace(reg.Nombre) ? "Superficie" : reg.Nombre;
            ed.WriteMessage($"\n  · «{nombre}»");

            // A. Ubicar el archivo
            string ruta = SuperficiesNucleo.ResolverRuta(reg, carpetas, File.Exists);
            if (ruta == null)
            {
                ed.WriteMessage($"\n    ⚠ No se encontró el LandXML («{reg.Archivo}» junto al dibujo, ni «{reg.ArchivoAbs}»). No se crea.");
                return false;
            }
            byte[] datos = File.ReadAllBytes(ruta);

            // B. ¿Es el mismo archivo que exportó la app?
            string sha = SuperficiesNucleo.Sha1Hex(datos);
            if (string.IsNullOrEmpty(reg.Sha1))
                ed.WriteMessage("\n    ⚠ El DXF no trae el SHA1 del archivo: no se puede comprobar que sea el exportado.");
            else if (!string.Equals(sha, reg.Sha1, StringComparison.OrdinalIgnoreCase))
            {
                ed.WriteMessage($"\n    ⚠ El archivo cambió después de exportar ({ruta}: SHA1 {sha}, esperado {reg.Sha1}). No se crea.");
                return false;
            }

            var civilDoc = CivilApplication.ActiveDocument;

            // D. ¿Ya hay una superficie con ese nombre?
            var nombres = new List<string>();
            using (var tr = db.TransactionManager.StartTransaction())
            {
                foreach (ObjectId sid in civilDoc.GetSurfaceIds())
                {
                    CivilDB.Surface s;
                    try { s = tr.GetObject(sid, OpenMode.ForRead) as CivilDB.Surface; } catch { continue; }
                    if (s == null) continue;
                    nombres.Add(s.Name);
                    if (!string.Equals(s.Name, nombre, StringComparison.OrdinalIgnoreCase) || !(s is CivilDB.TinSurface tin)) continue;
                    var m = Medir(tin);
                    if (m != null && SuperficiesNucleo.Coincide(reg, m))
                    {
                        ed.WriteMessage("\n    ✔ Ya estaba en el dibujo con los mismos datos: no se duplica.");
                        tr.Commit();
                        return false;
                    }
                }
                tr.Commit();
            }
            string nombreNuevo = SuperficiesNucleo.NombreLibre(nombre, nombres);
            if (nombreNuevo != nombre)
                ed.WriteMessage($"\n    · Ya existe otra «{nombre}» distinta: se crea como «{nombreNuevo}».");

            // C. Copia con las unidades del dibujo (Civil 3D no convierte)
            var uz = civilDoc.Settings.DrawingSettings.UnitZoneSettings;
            bool metros = uz.DrawingUnits == Autodesk.Civil.Settings.DrawingUnitType.Meters;
            bool pieTopo = false;
            try { pieTopo = uz.ImperialToMetricConversion == Autodesk.Civil.Settings.ImperialToMetricConversionType.UsSurveyFoot; } catch { }
            string unidadDib = SuperficiesNucleo.UnidadDelDibujo(metros, pieTopo);
            string texto = SuperficiesNucleo.Texto(datos);
            string unidadArch = SuperficiesNucleo.UnidadDelArchivo(texto);
            if (!string.IsNullOrEmpty(unidadArch) && !string.Equals(unidadArch, unidadDib, StringComparison.OrdinalIgnoreCase))
                ed.WriteMessage($"\n    · LandXML en «{unidadArch}», dibujo en «{unidadDib}»: los números ya están en el sistema del dibujo, se importan sin convertir.");
            string tmp = Path.Combine(Path.GetTempPath(), "pdfcad_superficie_" + Guid.NewGuid().ToString("N") + ".xml");
            File.WriteAllText(tmp, SuperficiesNucleo.ReescribirUnidades(texto, unidadDib), new System.Text.UTF8Encoding(false));

            ObjectId id = ObjectId.Null;
            var imp = civilDoc.Settings.LandXMLSettings.Import;
            bool? trasl = null, giro = null, pieAInt = null;
            try
            {
                try { trasl = imp.Translation.Translate; imp.Translation.Translate = false; } catch { }
                try { giro = imp.Rotation.Rotate; imp.Rotation.Rotate = false; } catch { }
                try { pieAInt = imp.SurfaceImport.ConvertSurveyFootToInternationalFoot; imp.SurfaceImport.ConvertSurveyFootToInternationalFoot = false; } catch { }

                using (var tr = db.TransactionManager.StartTransaction())
                {
                    id = CivilDB.TinSurface.CreateFromLandXML(db, nombreNuevo, tmp);
                    var s = (CivilDB.TinSurface)tr.GetObject(id, OpenMode.ForWrite);
                    // Capa: la que pone Civil 3D por defecto; si quedó en «0», la de topografía.
                    if (string.Equals(s.Layer, "0", StringComparison.OrdinalIgnoreCase) && AsegurarCapa(tr, db, CAPA_SUPERFICIE))
                        s.Layer = CAPA_SUPERFICIE;
                    try { if (s.IsOutOfDate) s.Rebuild(); } catch { }
                    tr.Commit();
                }
            }
            finally
            {
                try { if (trasl.HasValue) imp.Translation.Translate = trasl.Value; } catch { }
                try { if (giro.HasValue) imp.Rotation.Rotate = giro.Value; } catch { }
                try { if (pieAInt.HasValue) imp.SurfaceImport.ConvertSurveyFootToInternationalFoot = pieAInt.Value; } catch { }
                try { File.Delete(tmp); } catch { }
            }
            if (id.IsNull)
            {
                ed.WriteMessage("\n    ✗ Civil 3D no creó la superficie.");
                return false;
            }

            // E. Verificar contra el XDATA
            using (var tr = db.TransactionManager.StartTransaction())
            {
                var s = (CivilDB.TinSurface)tr.GetObject(id, OpenMode.ForRead);
                var m = Medir(s);
                if (m == null) ed.WriteMessage("\n    ⚠ No se pudieron leer las propiedades de la superficie creada.");
                else
                {
                    var lineas = SuperficiesNucleo.Comparar(reg, m, (x, y) =>
                    {
                        try { return s.FindElevationAtXY(x, y); } catch { return null; }
                    });
                    bool todo = true;
                    foreach (var l in lineas) { ed.WriteMessage("\n    " + l); todo &= l.Ok; }
                    ed.WriteMessage(todo
                        ? $"\n    ✔ «{nombreNuevo}» creada, idéntica a la de la app."
                        : $"\n    ⚠ «{nombreNuevo}» creada, pero NO coincide en todo con la de la app (revisa lo marcado ⚠).");
                }
                tr.Commit();
            }
            return true;
        }

        private static SuperficiesNucleo.Medido Medir(CivilDB.TinSurface s)
        {
            try
            {
                var g = s.GetGeneralProperties();
                var t = s.GetTinProperties();
                return new SuperficiesNucleo.Medido
                {
                    NPuntos = g.NumberOfPoints,
                    NTriangulos = t.NumberOfTriangles,
                    ZMin = g.MinimumElevation, ZMax = g.MaximumElevation,
                    XMin = g.MinimumCoordinateX, YMin = g.MinimumCoordinateY,
                    XMax = g.MaximumCoordinateX, YMax = g.MaximumCoordinateY,
                };
            }
            catch { return null; }
        }
    }
}
