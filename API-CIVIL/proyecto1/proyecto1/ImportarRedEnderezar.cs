using System;
using System.Collections.Generic;
using System.Linq;
using Autodesk.AutoCAD.EditorInput;
using Autodesk.AutoCAD.Geometry;

// ============================================================================
//  ENDEREZAR QUIEBRES MÍNIMOS (redes tipo PIPE: gravedad y conduit)
//   En Civil 3D cada tubo es un cilindro recto: dos tubos que se juntan en ángulo
//   SIN estructura se montan por dentro del giro y dejan una cuña abierta por
//   fuera (en planta y en 3D). Los quiebres casi rectos (≤ 2°, el vértice a
//   ≤ 0.25 ft de la recta) no existen en el plano: son vértices que dejó el
//   reconocimiento sobre una línea continua del PDF. Aquí se quitan ANTES de crear
//   la red y los dos tramos quedan en UN tubo recto (los extremos no se mueven:
//   ningún tubo vecino cambia). La app y el DXF no cambian.
//   Solo se quita un vértice si NO tiene nada: ni estructura (salvo un buzón
//   ocultado desde la app), ni curva, ni sólido, ni otra tubería que llegue a él,
//   ni es el ancla recta de un codo (vecino de un vértice curvo);
//   con la misma familia/tamaño a ambos lados y la cota del vértice sobre la
//   pendiente del tubo unido (un cambio de pendiente o una caída se conserva).
//   La decisión es PURA (EnderezarNucleo.cs); aquí solo se arman las entradas y
//   se reindexa lo que va por vértice/tramo.
// ============================================================================

namespace Civil3DBasico
{
    public partial class ComandosRedes
    {
        /// <summary>
        /// Quita de cada tubería de gravedad/conduit los vértices de quiebre mínimo
        /// sin nada encima (ver cabecera). `pies` = unidades del dibujo por pie.
        /// Devuelve cuántos vértices se quitaron.
        /// </summary>
        private static int EnderezarQuiebres(List<ImportPipe> pipes, List<ImportStruct> structs,
                                             List<ImportCrossConnect> cruces, double pies, Editor ed)
        {
            double tolNodo = 1.0 * pies;                   // mismo criterio que FindNearestStruct
            int total = 0;
            foreach (var ip in pipes)
            {
                if (string.Equals(ip.NetKind, "pressure", StringComparison.OrdinalIgnoreCase)) continue;
                var v = ip.Vertices;
                int n = v?.Count ?? 0;
                if (n < 3) continue;

                var bloq = new bool[n];
                var curva = new bool[n];
                for (int i = 1; i < n - 1; i++)
                {
                    bloq[i] = VerticeOcupado(ip, i, pipes, structs, cruces, tolNodo);
                    curva[i] = ip.NoManholeVerts.Contains(i) || ip.CurveRadiusByVert.ContainsKey(i);
                }
                var pieza = new string[n];
                for (int s = 0; s < n - 1; s++)
                    pieza[s] = ip.SegOverrides.TryGetValue(s, out var ov) ? ov.fam + "~" + ov.size : "";
                double[] zOut = InterpolateZ(ip, n, ip.VertexInv);
                double[] zIn = InterpolateZ(ip, n, ip.VertexInvIn);

                var quitar = EnderezarNucleo.VerticesAQuitar(
                    v.Select(p => p.X).ToList(), v.Select(p => p.Y).ToList(), zOut, zIn, bloq, pieza,
                    EnderezarNucleo.DESVIO_MAX_FT * pies, EnderezarNucleo.COTA_TOL_FT * pies, curva);
                if (quitar.Count == 0) continue;

                // Reindexar: `quedan[m]` = índice original del vértice m. Las cotas de
                // los que quedan se escriben explícitas (no se mueve ninguna).
                var fuera = new HashSet<int>(quitar);
                var quedan = Enumerable.Range(0, n).Where(i => !fuera.Contains(i)).ToList();
                var nuevo = new Dictionary<int, int>();
                for (int m = 0; m < quedan.Count; m++) nuevo[quedan[m]] = m;
                var vOut = new Dictionary<int, double>();
                var vIn = new Dictionary<int, double>();
                for (int m = 1; m < quedan.Count - 1; m++) { vOut[m] = zOut[quedan[m]]; vIn[m] = zIn[quedan[m]]; }
                ip.VertexInv = vOut; ip.VertexInvIn = vIn;
                ip.CurveRadiusByVert = ip.CurveRadiusByVert.Where(kv => nuevo.ContainsKey(kv.Key))
                                                           .ToDictionary(kv => nuevo[kv.Key], kv => kv.Value);
                ip.NoManholeVerts = new HashSet<int>(ip.NoManholeVerts.Where(nuevo.ContainsKey).Select(i => nuevo[i]));
                var segs = new Dictionary<int, (string fam, string size)>();
                for (int m = 0; m < quedan.Count - 1; m++)
                    if (ip.SegOverrides.TryGetValue(quedan[m], out var ov)) segs[m] = ov;
                ip.SegOverrides = segs;
                var tramos = ip.TramoPython ?? Enumerable.Range(0, n - 1).ToList();
                ip.TramoPython = Enumerable.Range(0, quedan.Count - 1).Select(m => tramos[quedan[m]]).ToList();
                ip.Vertices = quedan.Select(i => v[i]).ToList();

                total += quitar.Count;
                Dl(ed, $"\n  [ENDEREZAR] '{ip.Layer}' #{ip.PipeIdx}: vértice(s) {string.Join(",", quitar)} " +
                       $"(≤ {EnderezarNucleo.GIRO_MAX_DEG:0.#}°) quitados → tramos unidos en un tubo recto.");
            }
            if (total > 0)
                ed?.WriteMessage($"\n  · {total} quiebre(s) mínimo(s) (≤ {EnderezarNucleo.GIRO_MAX_DEG:0.#}°, " +
                                 $"≤ {EnderezarNucleo.DESVIO_MAX_FT:0.##} ft) enderezado(s): un tubo recto, sin cuñas ni solapes en la unión.");
            return total;
        }

        /// <summary>
        /// El vértice i de ip lleva algo: curva, estructura visible o sólido, conexión
        /// cruzada, u otro vértice (de otra tubería, o de la misma que no sea vecino:
        /// un lazo) a ≤ tolNodo.
        /// Un buzón OCULTADO desde la app no cuenta: el plugin no crea nada ahí.
        /// </summary>
        private static bool VerticeOcupado(ImportPipe ip, int i, List<ImportPipe> pipes,
                                           List<ImportStruct> structs, List<ImportCrossConnect> cruces, double tolNodo)
        {
            if (ip.NoManholeVerts.Contains(i) || ip.CurveRadiusByVert.ContainsKey(i)) return true;
            Point2d p = ip.Vertices[i];
            var st = FindNearestStruct(structs, p, tolNodo);
            if (st != null && (!st.Hidden || st.Solid)) return true;
            if (cruces != null && cruces.Any(c => new Point2d(c.X, c.Y).GetDistanceTo(p) < tolNodo)) return true;
            foreach (var otra in pipes)
            {
                var ov = otra.Vertices;
                if (ov == null) continue;
                for (int j = 0; j < ov.Count; j++)
                    if (!(ReferenceEquals(otra, ip) && Math.Abs(j - i) <= 1) && ov[j].GetDistanceTo(p) < tolNodo) return true;
            }
            return false;
        }
    }
}
