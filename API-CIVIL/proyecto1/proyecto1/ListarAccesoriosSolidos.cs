using System;
using System.Collections.Generic;
using System.Linq;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.EditorInput;
using Autodesk.AutoCAD.Runtime;

namespace Civil3DBasico
{
    // Lectura del property set (XDATA) de los accesorios generados como sólido
    // 3D. Civil 3D no muestra el XDATA en su interfaz, así que sin este comando
    // los datos existen en el dibujo pero son invisibles para el usuario.
    public class ListarAccesoriosSolidos
    {
        // Un accesorio concreto: se pincha y se leen sus datos.
        [CommandMethod("DATOS_ACCESORIO")]
        public void DatosAccesorio()
        {
            Document doc = Application.DocumentManager.MdiActiveDocument;
            Editor ed = doc.Editor;

            var pso = new PromptEntityOptions("\nSelecciona un accesorio (sólido 3D): ");
            pso.SetRejectMessage("\nDebe ser un sólido 3D generado por el plugin.");
            pso.AddAllowedClass(typeof(Solid3d), true);
            PromptEntityResult per = ed.GetEntity(pso);
            if (per.Status != PromptStatus.OK) return;

            using (Transaction tr = doc.Database.TransactionManager.StartTransaction())
            {
                var ent = tr.GetObject(per.ObjectId, OpenMode.ForRead) as Entity;
                var datos = WyeSolido.LeerXData(ent);
                if (datos == null)
                {
                    ed.WriteMessage("\n⚠ Ese sólido no tiene datos de accesorio " +
                        "(no lo generó el plugin, o se creó con una versión anterior).");
                }
                else
                {
                    ed.WriteMessage($"\n── Datos del accesorio ──────────────────────");
                    foreach (string d in datos)
                    {
                        int eq = d.IndexOf('=');
                        if (eq <= 0) { ed.WriteMessage($"\n  {d}"); continue; }
                        ed.WriteMessage($"\n  {d.Substring(0, eq).PadRight(20)} {d.Substring(eq + 1)}");
                    }
                    // ANGULO del XDATA = giro; en el codo el usuario lee el ángulo ENTRE tuberías.
                    string Campo(string k) => datos.Select(x => x.Split('='))
                        .Where(x => x.Length == 2 && x[0] == k).Select(x => x[1]).FirstOrDefault();
                    if (string.Equals(Campo("TIPO"), "ELBOW", StringComparison.OrdinalIgnoreCase) &&
                        double.TryParse(Campo("ANGULO"), System.Globalization.NumberStyles.Float,
                                        System.Globalization.CultureInfo.InvariantCulture, out double giro))
                        ed.WriteMessage($"\n  {"ENTRE TUBERÍAS".PadRight(20)} " +
                                        $"{AccesorioPropertySet.AnguloVisible("ELBOW", giro):0.##}° (ANGULO = giro)");
                    ed.WriteMessage("\n─────────────────────────────────────────────");
                }
                tr.Commit();
            }
        }

        // Todos los accesorios del dibujo, como tabla resumen. Sirve para
        // cómputos métricos: cuántas piezas de cada tipo y diámetro hay.
        [CommandMethod("LISTAR_ACCESORIOS")]
        public void ListarTodos()
        {
            Document doc = Application.DocumentManager.MdiActiveDocument;
            Editor ed = doc.Editor;
            Database db = doc.Database;

            using (Transaction tr = db.TransactionManager.StartTransaction())
            {
                var bt = (BlockTable)tr.GetObject(db.BlockTableId, OpenMode.ForRead);
                var ms = (BlockTableRecord)tr.GetObject(bt[BlockTableRecord.ModelSpace], OpenMode.ForRead);

                var filas = new List<Dictionary<string, string>>();
                foreach (ObjectId id in ms)
                {
                    if (id.ObjectClass.DxfName != "3DSOLID") continue;
                    var ent = tr.GetObject(id, OpenMode.ForRead) as Entity;
                    var datos = WyeSolido.LeerXData(ent);
                    if (datos == null) continue;
                    var fila = new Dictionary<string, string>();
                    foreach (string d in datos)
                    {
                        int eq = d.IndexOf('=');
                        if (eq > 0) fila[d.Substring(0, eq)] = d.Substring(eq + 1);
                    }
                    filas.Add(fila);
                }

                if (filas.Count == 0)
                {
                    ed.WriteMessage("\nNo hay accesorios generados por el plugin en este dibujo.");
                    tr.Commit();
                    return;
                }

                string V(Dictionary<string, string> f, string k) =>
                    f.TryGetValue(k, out string v) ? v : "";
                // Ángulo como lo ve el usuario (codo = entre las dos tuberías).
                string Ang(Dictionary<string, string> f) =>
                    double.TryParse(V(f, "ANGULO"), System.Globalization.NumberStyles.Float,
                                    System.Globalization.CultureInfo.InvariantCulture, out double a)
                        ? AccesorioPropertySet.AnguloVisible(V(f, "TIPO"), a).ToString("0.##", System.Globalization.CultureInfo.InvariantCulture)
                        : V(f, "ANGULO");

                ed.WriteMessage($"\n\n══ ACCESORIOS EN EL DIBUJO ({filas.Count}) ══");
                ed.WriteMessage($"\n{"TIPO",-7} {"ÁNGULO",7} {"Ø PRAL",7} {"Ø RAMAL",8} " +
                                $"{"LARGO",7}  {"COORD X",11} {"COORD Y",11} {"COTA",8}  RED");
                foreach (var f in filas.OrderBy(x => V(x, "TIPO")).ThenBy(x => V(x, "COORD_X")))
                {
                    ed.WriteMessage($"\n{V(f, "TIPO"),-7} {Ang(f),7} " +
                        $"{V(f, "DIAM_PRINCIPAL_IN"),7} {V(f, "DIAM_RAMAL_IN"),8} " +
                        $"{V(f, "LARGO_TOTAL_FT"),7}  {V(f, "COORD_X"),11} " +
                        $"{V(f, "COORD_Y"),11} {V(f, "COTA_EJE_FT"),8}  {V(f, "RED")}");
                }

                // Resumen por tipo y diámetro — lo que se lleva a un cómputo.
                ed.WriteMessage("\n\n── Resumen para cómputo ──");
                var resumen = filas
                    .GroupBy(f => $"{V(f, "TIPO")} Ø{V(f, "DIAM_PRINCIPAL_IN")}\" {Ang(f)}°")
                    .OrderByDescending(g => g.Count());
                foreach (var g in resumen)
                    ed.WriteMessage($"\n  {g.Count(),3} × {g.Key}");
                ed.WriteMessage("\n──────────────────────────\n");

                tr.Commit();
            }
        }
    }
}
