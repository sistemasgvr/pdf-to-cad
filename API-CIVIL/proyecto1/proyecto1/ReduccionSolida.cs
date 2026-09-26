using System;
using System.Collections.Generic;
using System.Linq;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.EditorInput;
using Autodesk.AutoCAD.Geometry;
using Exception = System.Exception;

// ============================================================================
//  Codo con reducción (dos tubos de distinto diámetro que además giran)
//
//  Antes se barría UN codo cuya sección se achicaba a lo largo de la curva (un
//  cono doblado): forma rara y sin equivalente comercial. Ahora, como en obra:
//
//      tubo grande ══════╗
//                        ║  CODO del diámetro MAYOR (forma uniforme)
//                        ╚═▶ REDUCCIÓN excéntrica ── tubo chico
//
//  · El codo va en el vértice, a la altura del EJE del tubo grande (antes se
//    centraba en el promedio de los dos ejes y ninguna boca coincidía).
//  · La reducción une el eje de cada tubo tal como está dibujado: con la misma
//    cota de fondo sale de fondo plano (excéntrica) y no se cambia ninguna cota.
//  · El tubo chico se recorta hasta la campana de la reducción.
// ============================================================================

namespace Civil3DBasico
{
    internal static partial class WyeSolido
    {
        // Largo del cuerpo cónico de la reducción, en diámetros del tubo mayor.
        private const double LARGO_REDUCCION_D = 1.25;

        internal class TuboJuntura
        {
            internal ObjectId PipeId;
            internal int Port;            // 0 = StartPoint en la juntura, 1 = EndPoint
            internal Point3d Cerca;       // extremo en la juntura (sobre su eje)
            internal Point3d Lejos;       // extremo opuesto
            internal double DiamFt;
        }

        // Crea el codo del diámetro mayor + la reducción hacia el menor. Devuelve
        // el Id del codo, o Null si no se pudo (el llamador cae al flujo normal).
        internal static ObjectId CrearCodoConReduccion(Database db, Transaction tr,
            TuboJuntura grande, TuboJuntura chico, double anguloDeg, string material, string red, Editor ed)
        {
            Vector3d dirGrande = grande.Lejos - grande.Cerca;
            Vector3d u = chico.Lejos - chico.Cerca;
            if (dirGrande.Length < 1e-6 || u.Length < 1e-6) return ObjectId.Null;
            double largoChico = u.Length;
            u = u.GetNormal();
            double d1 = grande.DiamFt, d2 = chico.DiamFt;

            // 1) Codo uniforme del diámetro mayor, con centro en el eje del tubo
            //    grande. El brazo del lado chico no lleva tubo: ahí entra la reducción.
            Point3d centro = grande.Cerca;
            var brazos = new List<Brazo>
            {
                new Brazo { Direccion = dirGrande, DiamFt = d1, PipeId = grande.PipeId, Port = grande.Port },
                new Brazo { Direccion = u, DiamFt = d1 },
            };
            var infoCodo = new Info
            {
                Tipo = "ELBOW", AnguloDeg = anguloDeg, DiamPrincipalIn = d1 * 12.0, DiamRamalIn = d1 * 12.0,
                Material = material, Red = red,
            };
            ObjectId codoId = Crear(db, tr, centro, brazos, infoCodo, ed);
            if (codoId == ObjectId.Null) return ObjectId.Null;

            // 2) Reducción: nace donde moriría un tubo Ø mayor dentro de la campana
            //    del codo y termina sobre el eje del tubo chico.
            Point3d r0 = centro + u * brazos[1].AlcanceTuboFt;
            double s0 = (r0 - chico.Cerca).DotProduct(u);
            double largoRed = d1 * LARGO_REDUCCION_D;
            Point3d r1 = chico.Cerca + u * (s0 + largoRed);
            double lCamp = d2 * LARGO_CAMPANA_D;
            Point3d punta = r1 + u * (lCamp * CALADO_EN_CAMPANA - SOLAPE_EXTRA_FT);   // donde muere el tubo chico
            double recorte = (punta - chico.Cerca).DotProduct(u);
            if (recorte > largoChico - 0.05)
            {
                ed?.WriteMessage($"\n    ⚠ [REDUCCION] El tubo Ø{d2 * 12:F0}\" mide {largoChico:F2} ft y la reducción " +
                    $"necesita {recorte:F2} ft: se deja el codo sin reducción.");
                return codoId;
            }

            Solid3d cuerpo = null;
            try
            {
                using (var c0 = new Circle(r0, u, d1 / 2.0))
                using (var c1 = new Circle(r1, u, d2 / 2.0))
                {
                    cuerpo = new Solid3d();
                    cuerpo.CreateLoftedSolid(new Entity[] { c0, c1 }, new Entity[0], null,
                                             new LoftOptionsBuilder().ToLoftOptions());
                }
                // Campana en la boca chica, montada sobre el cono (como en el codo).
                double monta = d2 * MONTAJE_CAMPANA_D;
                var camp = Cilindro(d2 / 2.0 + HOLGURA_FT + PARED_FT, lCamp + monta,
                                    r1 - u * monta + u * ((lCamp + monta) / 2.0), u);
                if (camp != null)
                {
                    try { cuerpo.BooleanOperation(BooleanOperationType.BoolUnite, camp); }
                    catch { try { camp.Dispose(); } catch { } }
                }

                AsegurarCapa(db, tr);
                cuerpo.Layer = CAPA;
                var bt = (BlockTable)tr.GetObject(db.BlockTableId, OpenMode.ForRead);
                var ms = (BlockTableRecord)tr.GetObject(bt[BlockTableRecord.ModelSpace], OpenMode.ForWrite);
                ObjectId id = ms.AppendEntity(cuerpo);
                tr.AddNewlyCreatedDBObject(cuerpo, true);

                var brazosRed = new List<Brazo>
                {
                    new Brazo { Direccion = -u, DiamFt = d1, LargoCuerpoFt = 0 },
                    new Brazo { Direccion = u, DiamFt = d2, LargoCuerpoFt = largoRed },
                };
                var infoRed = new Info
                {
                    Tipo = "REDUCER", AnguloDeg = 0, DiamPrincipalIn = d1 * 12.0, DiamRamalIn = d2 * 12.0,
                    Material = material, Red = red,
                };
                Point3d medio = r0 + (r1 - r0) * 0.5;
                GrabarXData(db, tr, cuerpo, infoRed, brazosRed, medio, ed);
                AccesorioPropertySet.AplicarDesdeXData(db, tr, cuerpo, ed);
                Creadas.Add(new Registro { SolidId = id, Tipo = "REDUCER", Centro = medio,
                                           Brazos = brazosRed.Select(b => b.Copia()).ToList() });

                // 3) El tubo chico muere dentro de la campana de la reducción.
                var pp = (Autodesk.Civil.DatabaseServices.PressurePipe)tr.GetObject(chico.PipeId, OpenMode.ForWrite);
                if (chico.Port == 0) pp.StartPoint = punta; else pp.EndPoint = punta;

                double desnivel = r0.Z - r1.Z;
                ed?.WriteMessage($"\n    · [REDUCCION] Codo Ø{d1 * 12:F0}\" + reducción {d1 * 12:F0}×{d2 * 12:F0}\" " +
                    $"de {largoRed:F2} ft; ejes a {desnivel:F2} ft de diferencia " +
                    $"({(Math.Abs(Math.Abs(desnivel) - (d1 - d2) / 2.0) < 0.02 ? "excéntrica, fondo plano" : Math.Abs(desnivel) < 0.02 ? "concéntrica" : "excéntrica, une los ejes dibujados")}); " +
                    $"tubo chico recortado {recorte:F2} ft.");
                return codoId;
            }
            catch (Exception ex)
            {
                try { cuerpo?.Dispose(); } catch { }
                ed?.WriteMessage($"\n    ⚠ [REDUCCION] No se pudo generar la reducción: {ex.Message}");
                return codoId;
            }
        }
    }
}
