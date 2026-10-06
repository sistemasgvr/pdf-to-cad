using System;
using System.Collections.Generic;
using System.Linq;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.EditorInput;
using Autodesk.AutoCAD.Geometry;
using CivilDB = Autodesk.Civil.DatabaseServices;
using AecPD = Autodesk.Aec.PropertyData;
using Exception = System.Exception;

// ============================================================================
//  DATOS EXTENDIDOS DE LA APP EN LA RED (pedido del usuario 2026-10-06)
//   Lo que la app muestra en «Ver datos extendidos» viaja en el DXF como XD_*
//   (automáticos del reconocimiento: capa OCG de origen, xref, capa, disciplina,
//   sistema, ubicación, estado, modificadores, origen «PDF · Hoja N») y XDU_*
//   (campos del usuario). Al final del import:
//     - cada tubería y accesorio de las redes creadas lleva «PDFCAD_Utilidad»:
//       Utilidad (capa de la app), Numero_App (su número en la lista al exportar),
//       Red + los datos extendidos de la utilidad de la que salió;
//     - cada estructura lleva «PDFCAD_Estructura»: Codigo (BZ-3, CAJA-2…), Red +
//       los datos extendidos de la estructura de la app en ese mismo punto.
//   Se ven al seleccionar la pieza: Propiedades → «Datos extendidos».
//   Mismo reparto que la capa (ImportarRedCapas.cs): si una red junta varias
//   utilidades, cada pieza toma la de la polilínea más cercana.
// ============================================================================

namespace Civil3DBasico
{
    public partial class ComandosRedes
    {
        private static readonly DefinicionPS PS_UTILIDAD = new DefinicionPS
        {
            Nombre = "PDFCAD_Utilidad",
            Descripcion = "Utilidad de la app PDF-a-CAD de la que salió la pieza y sus datos extendidos",
            Tipos = new[] { typeof(CivilDB.Pipe), typeof(CivilDB.PressurePipe),
                            typeof(CivilDB.PressureFitting), typeof(CivilDB.PressureAppurtenance) },
            Fijas = new[]
            {
                ("Utilidad",   AecPD.DataType.Text,    "Tipo de utilidad en la app (capa: ELECTRICO, TELECOM, AGUA…)"),
                ("Numero_App", AecPD.DataType.Integer, "Número de la utilidad en la lista de la app al exportar"),
                ("Red",        AecPD.DataType.Text,    "Red de Civil 3D"),
            },
        };

        private static readonly DefinicionPS PS_ESTRUCTURA = new DefinicionPS
        {
            Nombre = "PDFCAD_Estructura",
            Descripcion = "Estructura (buzón/caja) de la app PDF-a-CAD y sus datos extendidos",
            Tipos = new[] { typeof(CivilDB.Structure) },
            Fijas = new[]
            {
                ("Codigo", AecPD.DataType.Text, "Código de la estructura en la app (BZ-N, CAJA-N…)"),
                ("Red",    AecPD.DataType.Text, "Red de Civil 3D"),
            },
        };

        private const double TOL_ESTRUCTURA_FT = 0.5;

        /// <summary>Property Sets con los datos extendidos de la app en cada pieza de las
        /// redes creadas (`redes` = red → polilíneas de origen).</summary>
        private static void AdjuntarDatosExtendidos(Editor ed, Database db,
            Dictionary<ObjectId, List<ImportPipe>> redes, List<ImportStruct> structs)
        {
            if (redes == null || redes.Count == 0) return;
            int nPiezas = 0, nEstructuras = 0, nFallos = 0;
            double tol = TOL_ESTRUCTURA_FT * FactorConversion("ft", db);
            using (Transaction tr = db.TransactionManager.StartTransaction())
            {
                try
                {
                    foreach (var kv in redes)
                    {
                        if (kv.Key.IsNull || kv.Key.IsErased) continue;
                        var fuentes = (kv.Value ?? new List<ImportPipe>()).Where(p => p != null).ToList();
                        if (fuentes.Count == 0) continue;
                        string red = NombreDeRed(tr, kv.Key);
                        foreach (ObjectId id in PiezasDeRed(tr, kv.Key))
                        {
                            var ent = tr.GetObject(id, OpenMode.ForRead) as Entity;
                            if (ent == null) continue;
                            if (ent is CivilDB.Structure s)
                            {
                                var st = EstructuraEn(structs, new Point2d(s.Position.X, s.Position.Y), tol);
                                if (st == null) continue;          // estructura nula de un extremo libre
                                var fijas = new Dictionary<string, object> { ["Codigo"] = st.Id ?? "", ["Red"] = red };
                                if (PropertySetPdfcad.Aplicar(db, tr, ent, PS_ESTRUCTURA, fijas, st.Extendidos, ed)) nEstructuras++;
                                else nFallos++;
                                continue;
                            }
                            var f = fuentes.Count == 1 ? fuentes[0] : FuenteMasCercana(fuentes, PuntoDePieza(ent));
                            if (f == null) continue;
                            int idx = f.IdxOrigen >= 0 ? f.IdxOrigen : f.PipeIdx;
                            var fp = new Dictionary<string, object>
                            {
                                ["Utilidad"] = string.IsNullOrWhiteSpace(f.Utilidad) ? (f.Layer ?? "") : f.Utilidad,
                                ["Numero_App"] = idx >= 0 ? idx + 1 : 0,
                                ["Red"] = red,
                            };
                            if (PropertySetPdfcad.Aplicar(db, tr, ent, PS_UTILIDAD, fp, f.Extendidos, ed)) nPiezas++;
                            else nFallos++;
                        }
                    }
                    tr.Commit();
                }
                catch (Exception ex)
                {
                    tr.Abort();
                    ed.WriteMessage($"\n(No se pudieron escribir los datos extendidos en la red: {ex.Message})");
                    return;
                }
            }
            if (nPiezas + nEstructuras > 0)
                ed.WriteMessage($"\n  · Datos extendidos (Property Sets «{PS_UTILIDAD.Nombre}»/«{PS_ESTRUCTURA.Nombre}»): " +
                                $"{nPiezas} tubería(s)/accesorio(s), {nEstructuras} estructura(s).");
            if (nFallos > 0)
                ed.WriteMessage($"\n  ⚠ {nFallos} pieza(s) sin datos extendidos (ver avisos [PROPERTY SET]).");
        }

        private static string NombreDeRed(Transaction tr, ObjectId netId)
        {
            try
            {
                var obj = tr.GetObject(netId, OpenMode.ForRead);
                if (obj is CivilDB.Network n) return n.Name ?? "";
                if (obj is CivilDB.PressurePipeNetwork pn) return pn.Name ?? "";
            }
            catch { }
            return "";
        }

        /// <summary>Estructura de la app en ese punto (la más cercana a ≤ tol).</summary>
        private static ImportStruct EstructuraEn(List<ImportStruct> structs, Point2d p, double tol)
        {
            ImportStruct mejor = null;
            double dMin = tol;
            foreach (var st in structs ?? new List<ImportStruct>())
            {
                if (st == null || st.Solid) continue;
                double d = st.Location.GetDistanceTo(p);
                if (d <= dMin) { dMin = d; mejor = st; }
            }
            return mejor;
        }
    }
}
