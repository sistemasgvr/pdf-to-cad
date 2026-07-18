using System;
using System.Collections.Generic;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.EditorInput;
using Autodesk.AutoCAD.Runtime;
using Autodesk.Civil.ApplicationServices;
using CivilDB = Autodesk.Civil.DatabaseServices;
using Exception = System.Exception;

// ============================================================================
//  HERRAMIENTAS de CORREDOR simplificadas:
//   · CREAR_CORREDOR_FACIL  → crea el corredor y, al final, detecta los TARGETS
//                             del assembly y te deja asignarlos (superficie/offset...).
//   · ASIGNAR_TARGETS_CORREDOR → hace lo mismo sobre un corredor que YA existe.
//  Archivo separado para no tocar Corredores.cs.
// ============================================================================

namespace Civil3DBasico
{
    public class ComandosCorredorHerramientas
    {
        // =====================================================================
        // CREAR_CORREDOR_FACIL — eje + perfil + assembly + nombre + frecuencia,
        //   y al terminar te pregunta y ASIGNA los targets del assembly.
        // =====================================================================
        [CommandMethod("CREAR_CORREDOR_FACIL")]
        public void CrearCorredorFacil()
        {
            Document doc = Application.DocumentManager.MdiActiveDocument;
            Editor ed = doc.Editor;
            Database db = doc.Database;
            CivilDocument civilDoc = CivilApplication.ActiveDocument;

            ObjectId alignId = PedirUno(ed, "Seleccione el EJE (alignment):", false, typeof(CivilDB.Alignment));
            if (alignId == ObjectId.Null) return;
            ObjectId profId = PedirUno(ed, "Seleccione el PERFIL (rasante) de ese eje:", false, typeof(CivilDB.Profile));
            if (profId == ObjectId.Null) return;
            ObjectId asmId = PedirUno(ed, "Seleccione el ASSEMBLY (sección tipo):", false, typeof(CivilDB.Assembly));
            if (asmId == ObjectId.Null) return;

            PromptStringOptions pso = new PromptStringOptions("\nNombre del corredor:");
            pso.AllowSpaces = true;
            PromptResult pnr = ed.GetString(pso);
            if (pnr.Status != PromptStatus.OK || string.IsNullOrWhiteSpace(pnr.StringResult)) return;
            string nombre = pnr.StringResult.Trim();

            PromptDoubleOptions pfo = new PromptDoubleOptions("\nFrecuencia (intervalo entre secciones, m):")
            { AllowNegative = false, AllowZero = false, DefaultValue = 5.0, UseDefaultValue = true };
            PromptDoubleResult pfr = ed.GetDouble(pfo);
            if (pfr.Status != PromptStatus.OK) return;
            double freq = pfr.Value;

            using (Transaction tr = db.TransactionManager.StartTransaction())
            {
                try
                {
                    ObjectId corridorId = civilDoc.CorridorCollection.Add(nombre, "BL-1", alignId, profId, "R-1", asmId);
                    CivilDB.Corridor corridor = (CivilDB.Corridor)tr.GetObject(corridorId, OpenMode.ForWrite);
                    ConfigurarFrecuencia(corridor.Baselines[0].BaselineRegions[0], freq);

                    // Detectar y asignar targets del assembly (superficie / offset / elevación)
                    PromptKeywordOptions pkT = new PromptKeywordOptions("\n¿Asignar ahora los objetivos (targets) del assembly? [Si/No] <Si>:", "Si No");
                    pkT.AllowNone = true;
                    PromptResult rkT = ed.GetKeywords(pkT);
                    if (!(rkT.Status == PromptStatus.OK && rkT.StringResult == "No"))
                        AsignarTargets(ed, corridor);

                    corridor.Rebuild();
                    tr.Commit();
                    ed.WriteMessage($"\n✓ Corredor '{nombre}' creado (frecuencia {freq:F1} m).");
                }
                catch (Exception ex)
                {
                    ed.WriteMessage($"\nError: {ex.Message}");
                    ed.WriteMessage("\n(Comprueba que el Profile pertenezca al Alignment seleccionado.)");
                    tr.Abort();
                }
            }
        }

        // =====================================================================
        // ASIGNAR_TARGETS_CORREDOR — sobre un corredor existente: lista los targets
        //   que pide el assembly y te deja asignar el objeto a cada uno.
        // =====================================================================
        [CommandMethod("ASIGNAR_TARGETS_CORREDOR")]
        public void AsignarTargetsCorredor()
        {
            Document doc = Application.DocumentManager.MdiActiveDocument;
            Editor ed = doc.Editor;
            Database db = doc.Database;

            PromptEntityOptions peo = new PromptEntityOptions("\nSeleccione el CORREDOR:");
            peo.SetRejectMessage("\nDebe ser un corredor.");
            peo.AddAllowedClass(typeof(CivilDB.Corridor), true);
            PromptEntityResult per = ed.GetEntity(peo);
            if (per.Status != PromptStatus.OK) return;

            using (Transaction tr = db.TransactionManager.StartTransaction())
            {
                try
                {
                    CivilDB.Corridor corridor = (CivilDB.Corridor)tr.GetObject(per.ObjectId, OpenMode.ForWrite);
                    bool algo = AsignarTargets(ed, corridor);
                    if (algo) corridor.Rebuild();
                    tr.Commit();
                    ed.WriteMessage(algo ? "\n✓ Targets asignados y corredor reconstruido." : "\n(No se asignó ningún target.)");
                }
                catch (Exception ex)
                {
                    ed.WriteMessage($"\nError: {ex.Message}");
                    tr.Abort();
                }
            }
        }

        // ---------- Núcleo: recorre los targets y deja asignar cada uno ----------
        private bool AsignarTargets(Editor ed, CivilDB.Corridor corridor)
        {
            CivilDB.SubassemblyTargetInfoCollection targets = corridor.GetTargets();
            if (targets == null || targets.Count == 0)
            {
                ed.WriteMessage("\nEste assembly no pide objetivos (targets): no hay nada que asignar.");
                return false;
            }

            ed.WriteMessage($"\nEl assembly expone {targets.Count} objetivo(s). En cada uno: selecciona un objeto o Enter para SALTAR.");
            int asignados = 0;
            for (int i = 0; i < targets.Count; i++)
            {
                CivilDB.SubassemblyTargetInfo ti = targets[i];
                ed.WriteMessage($"\n\n▸ Objetivo '{ti.DisplayName}'  [{ti.TargetType}]  (subassembly: {ti.SubassemblyName})");

                ObjectId sel = ObjectId.Null;
                switch (ti.TargetType)
                {
                    case CivilDB.SubassemblyLogicalNameType.Surface:
                        sel = PedirUno(ed, "  → SUPERFICIE para este objetivo (Enter = saltar):", true, typeof(CivilDB.TinSurface));
                        break;

                    case CivilDB.SubassemblyLogicalNameType.Offset:
                    case CivilDB.SubassemblyLogicalNameType.OffsetPipe:
                        sel = PedirUno(ed, "  → EJE / polilínea / feature line para el offset (Enter = saltar):", true,
                                       typeof(CivilDB.Alignment), typeof(CivilDB.FeatureLine), typeof(Polyline), typeof(Polyline3d));
                        break;

                    case CivilDB.SubassemblyLogicalNameType.Elevation:
                    case CivilDB.SubassemblyLogicalNameType.ElevationPipe:
                    case CivilDB.SubassemblyLogicalNameType.Profile:
                        sel = PedirUno(ed, "  → PERFIL / feature line para la elevación (Enter = saltar):", true,
                                       typeof(CivilDB.Profile), typeof(CivilDB.FeatureLine));
                        break;

                    case CivilDB.SubassemblyLogicalNameType.Alignment:
                        sel = PedirUno(ed, "  → EJE (alignment) (Enter = saltar):", true, typeof(CivilDB.Alignment));
                        break;

                    default:
                        ed.WriteMessage("\n  (Tipo no soportado por el asistente; saltado.)");
                        break;
                }

                if (sel != ObjectId.Null)
                {
                    ObjectIdCollection oc = new ObjectIdCollection();
                    oc.Add(sel);
                    ti.TargetIds = oc;
                    asignados++;
                    ed.WriteMessage("\n  ✓ Asignado.");
                }
                else ed.WriteMessage("\n  (saltado)");
            }

            corridor.SetTargets(targets);
            ed.WriteMessage($"\n\n{asignados} de {targets.Count} objetivo(s) asignado(s).");
            return asignados > 0;
        }

        // Pide UNA entidad de los tipos permitidos. allowNone=true permite Enter para saltar.
        private ObjectId PedirUno(Editor ed, string msg, bool allowNone, params Type[] clases)
        {
            PromptEntityOptions peo = new PromptEntityOptions("\n" + msg);
            peo.AllowNone = allowNone;
            peo.SetRejectMessage("\n  (Tipo no válido; intenta con otro objeto.)");   // DEBE ir antes de AddAllowedClass
            foreach (Type c in clases) peo.AddAllowedClass(c, false);
            PromptEntityResult per = ed.GetEntity(peo);
            return per.Status == PromptStatus.OK ? per.ObjectId : ObjectId.Null;
        }

        // Frecuencia para que el corredor siga bien el eje (igual que en Corredores.cs).
        private void ConfigurarFrecuencia(CivilDB.BaselineRegion region, double freq)
        {
            CivilDB.AppliedAssemblySetting fs = region.AppliedAssemblySetting;
            fs.FrequencyAlongTangents = freq;
            fs.FrequencyAlongCurves = freq;
            fs.FrequencyAlongSpirals = freq;
            fs.FrequencyAlongProfileCurves = freq;
            fs.AppliedAtHorizontalGeometryPoints = true;
            fs.AppliedAtProfileGeometryPoints = true;
            fs.AppliedAtProfileHighLowPoints = true;
        }
    }
}
