using System;
using System.Collections.Generic;
using System.Linq;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.EditorInput;
using Autodesk.AutoCAD.Geometry;
using CivilDB = Autodesk.Civil.DatabaseServices;
using PresStyles = Autodesk.Civil.DatabaseServices.Styles;
using Exception = System.Exception;

// ============================================================================
//  JUNTURAS de redes a presión — decisión de tipo/tamaño de accesorio
//  (Codo/Reductor/Unión/Tee/Cruz) compartida entre:
//    · IMPORTAR_RED (ImportarRed.cs, ComandosRedes.CrearRedPresionCompleta) —
//      antes reinventaba esto mal (solo Codo, diámetro de un solo lado).
//    · UNIR_TUBERIAS_PRESION / UNIR_VARIAS_PRESION (RedesPresion.cs /
//      RedesPresionRamales.cs) — ya tenían la lógica correcta, ahora extraída
//      aquí para que import la reutilice en vez de duplicarla.
//    · CORREGIR_FITTINGS_PRESION (RedesPresion.cs, CorregirFittingsDeRed).
// ============================================================================

namespace Civil3DBasico
{
    public partial class ComandosPresion
    {
        // Modo de prueba (2026-09-23): las Y, Tee y codos se generan como
        // Solid3d con la geometría real de la juntura en vez de buscarlos en el
        // catálogo. Evita tener que crear cientos de familias para cubrir cada
        // ángulo × diámetro. En false, vuelve al flujo de catálogo (intacto).
        internal const bool FITTING_COMO_SOLIDO = true;

        // Ángulo del RAMAL contra el eje del tronco, en una juntura de 3 tubos.
        // Mismo criterio que usa la selección de Wye: de las 3 particiones
        // posibles gana la de tronco más recto, y el ramal se mide contra ese
        // eje (que es como el catálogo nombra sus piezas: 30/45/60/90°).
        internal static double AnguloRamalDeTres(List<Vector3d> salidas)
        {
            if (salidas == null || salidas.Count != 3) return 0;
            var n = salidas.Select(v => v.Length > 1e-9 ? v.GetNormal() : Vector3d.XAxis).ToList();
            double mejorQuiebre = double.MaxValue, angRamal = 0;
            for (int br = 0; br < 3; br++)
            {
                int a = (br + 1) % 3, b = (br + 2) % 3;
                double angTronco = n[a].GetAngleTo(n[b]) * 180.0 / Math.PI;
                double quiebre = Math.Abs(180.0 - angTronco);
                if (quiebre >= mejorQuiebre) continue;
                mejorQuiebre = quiebre;
                // Eje del tronco = a→b; el ramal se mide contra él.
                Vector3d eje = (n[b] - n[a]);
                if (eje.Length < 1e-9) { angRamal = 90.0; continue; }
                double ang = n[br].GetAngleTo(eje.GetNormal()) * 180.0 / Math.PI;
                angRamal = ang > 90.0 ? 180.0 - ang : ang;
            }
            return angRamal;
        }

        // Material del tubo para el XDATA de la pieza. La propiedad puede no
        // existir según versión/catálogo, así que nunca debe tumbar el import.
        private static string SeguroMaterial(CivilDB.PressurePipe pp)
        {
            try { return pp?.PartDescription ?? ""; } catch { return ""; }
        }

        private static string SeguroNombreRed(CivilDB.PressurePipeNetwork net)
        {
            try { return net?.Name ?? ""; } catch { return ""; }
        }

        // Un sitio físico donde coinciden 2+ extremos de tubería (dentro de la
        // tolerancia de AgruparJunturas). Miembros = (pipe, puerto en la juntura:
        // 0=StartPoint, 1=EndPoint).
        internal class Juntura
        {
            public Point3d Ubicacion;
            public List<(ObjectId PipeId, int Port)> Miembros = new List<(ObjectId, int)>();
        }

        // Extrae el ángulo (en grados) de una descripción de PartSize, aceptando
        // AMBOS formatos que usan los catálogos de presión: símbolo de grado
        // ("90°"/"90º") y la palabra "degree" en cualquier capitalización
        // ("90 Degree", "90 degree"). Antes había DOS regex distintas en dos
        // archivos (MatchFitting buscaba el símbolo; _ExtraerAngulo buscaba la
        // palabra sin IgnoreCase) — si el catálogo real usaba el formato que la
        // regex de turno no cubría, el ángulo se perdía en silencio y el codo
        // elegido quedaba a la suerte de un desempate por diámetro únicamente.
        internal static double? ExtraerAnguloDeDescripcion(string desc)
        {
            if (string.IsNullOrEmpty(desc)) return null;
            var m = System.Text.RegularExpressions.Regex.Match(desc,
                @"(\d{1,3}(?:\.\d+)?)\s*(?:[°º]|degree)",
                System.Text.RegularExpressions.RegexOptions.IgnoreCase);
            if (m.Success && double.TryParse(m.Groups[1].Value,
                System.Globalization.NumberStyles.Float,
                System.Globalization.CultureInfo.InvariantCulture, out double v))
                return v;
            return null;
        }

        // Extrae el primer número de diámetro (en pulgadas) de una descripción
        // de PartSize. Ej "10 in Elbow 90°" → 10.0; "48 pulg. …" → 48.0.
        // LIMITACIÓN: para descripciones multi-diámetro ("12 in x 12 in x 6 in
        // Tee") solo devuelve el PRIMER número — no distingue diámetro de paso
        // del de ramal. Suficiente para elegir el fitting por el diámetro
        // dominante (igual que ya hacía el código existente), no para mapear
        // cada puerto a su tamaño específico.
        internal static double ExtraerDiametroDeDescripcion(string desc)
        {
            if (string.IsNullOrEmpty(desc)) return 0;
            var m = System.Text.RegularExpressions.Regex.Match(desc,
                @"(\d+(?:\.\d+)?)\s*(?:in|pulg|""|\bin\b)",
                System.Text.RegularExpressions.RegexOptions.IgnoreCase);
            if (m.Success && double.TryParse(m.Groups[1].Value,
                System.Globalization.NumberStyles.Float,
                System.Globalization.CultureInfo.InvariantCulture, out double v))
                return v;
            m = System.Text.RegularExpressions.Regex.Match(desc, @"(\d+(?:\.\d+)?)");
            if (m.Success && double.TryParse(m.Groups[1].Value,
                System.Globalization.NumberStyles.Float,
                System.Globalization.CultureInfo.InvariantCulture, out double v2))
                return v2;
            return 0;
        }

        // Extrae los dos diámetros (trunk, branch) de la descripción de un Tee.
        // Formatos típicos:
        //   "tee-14 in x 6 in-push on-..."  → (14, 6)
        //   "tee-6 in-push on-..."          → (6, 6)  [straight Tee]
        //   "tee 8 x 4"                     → (8, 4)
        // Si no hay dos valores, devuelve (única, única).
        internal static (double trunk, double branch) ExtraerDosDiametrosDeTee(string desc)
        {
            if (string.IsNullOrEmpty(desc)) return (0, 0);
            var matches = System.Text.RegularExpressions.Regex.Matches(desc,
                @"(\d+(?:\.\d+)?)\s*(?:in|pulg|""|\bin\b)",
                System.Text.RegularExpressions.RegexOptions.IgnoreCase);
            var vals = new List<double>();
            foreach (System.Text.RegularExpressions.Match m in matches)
            {
                if (double.TryParse(m.Groups[1].Value,
                        System.Globalization.NumberStyles.Float,
                        System.Globalization.CultureInfo.InvariantCulture,
                        out double v))
                    vals.Add(v);
            }
            if (vals.Count >= 2) return (vals[0], vals[1]);
            if (vals.Count == 1) return (vals[0], vals[0]);
            return (0, 0);
        }

        // Busca un Tee cuyo TRUNK matchee `trunkIn` y cuyo BRANCH matchee
        // `branchIn`. Puntúa por |Δtrunk| + |Δbranch|, prefiere el más
        // cercano. Fallback: si no encuentra ninguno decente (score > 4"),
        // devuelve null y el llamador decide qué hacer.
        internal static PresStyles.PressurePartSize BuscarTeePorTrunkYBranch(
            List<PresStyles.PressurePartSize> fittings, double trunkIn, double branchIn)
        {
            if (fittings == null) return null;
            var candidatos = fittings
                .Where(f => f.PartType == CivilDB.PressurePartType.Tee)
                .Select(f =>
                {
                    var (t, b) = ExtraerDosDiametrosDeTee(f.Description);
                    return new { Part = f, T = t, B = b,
                                 Score = Math.Abs(t - trunkIn) + Math.Abs(b - branchIn) };
                }).ToList();
            if (candidatos.Count == 0) return null;
            return candidatos.OrderBy(c => c.Score).First().Part;
        }

        // Decide qué TIPO de accesorio corresponde a una juntura de N tuberías,
        // con la MISMA lógica que ya usaban (por separado) UNIR_TUBERIAS_PRESION
        // (2 tubos: Reductor si difieren en diámetro, Codo si hay deflexión,
        // Unión si no) y UNIR_VARIAS_PRESION (3 tubos → Tee, 4 → Cruz) — extraída
        // aquí para que el import automático use la misma decisión en vez de
        // reinventarla. d1/d2/deflexDeg solo se usan cuando nMiembros==2.
        // Devuelve null para 1 miembro (no es juntura) o 5+ (no soportado).
        internal static CivilDB.PressurePartType? DecidirTipoFitting(
            int nMiembros, double d1, double d2, double deflexDeg)
        {
            if (nMiembros == 2)
                return (Math.Abs(d1 - d2) > 1e-6) ? CivilDB.PressurePartType.Reducer :
                       (Math.Abs(deflexDeg) > 1.0) ? CivilDB.PressurePartType.Elbow :
                       CivilDB.PressurePartType.Coupling;
            if (nMiembros == 3) return CivilDB.PressurePartType.Tee;
            if (nMiembros == 4) return CivilDB.PressurePartType.Cross;
            return null;
        }

        // Discriminador Tee vs Y para junturas de 3 tuberías, según los ángulos
        // entre los vectores QUE SALEN de la juntura hacia el extremo lejano
        // de cada tubo. Si ALGÚN par forma un ángulo cercano a 180° (colineales,
        // tol ±20°) hay una recta clara pasando por el nudo con un ramal → Tee.
        // Si NINGÚN par es colineal (típicamente los tres ángulos ~120°) → Y (Wye).
        internal static CivilDB.PressurePartType DecidirTeeOWye(
            List<Vector3d> vectoresSalida, double tolColinealDeg = 20.0)
        {
            if (vectoresSalida == null || vectoresSalida.Count != 3)
                return CivilDB.PressurePartType.Tee;
            var d = vectoresSalida.Select(v => v.Length > 1e-9 ? v.GetNormal() : Vector3d.XAxis).ToList();
            // Buscar si algún par es casi colineal (tronco recto).
            for (int i = 0; i < 3; i++)
                for (int j = i + 1; j < 3; j++)
                {
                    double ang = d[i].GetAngleTo(d[j]) * 180.0 / Math.PI;
                    if (ang >= 180.0 - tolColinealDeg)
                    {
                        // Par colineal encontrado → el ramal es el tercero.
                        int br = 3 - i - j; // índice del ramal
                        // Ángulo del ramal contra el eje del tronco.
                        double angRamal = d[br].GetAngleTo(d[i]) * 180.0 / Math.PI;
                        if (angRamal > 90) angRamal = 180.0 - angRamal;
                        // Solo Tee si el ramal está cerca de 90° (±20°).
                        // Si el ramal se desvía mucho de 90° (ej. 45°), una
                        // pieza Tee estándar no encaja → usar Wye.
                        if (angRamal >= 70.0) return CivilDB.PressurePartType.Tee;
                        return CivilDB.PressurePartType.Wye;
                    }
                }
            return CivilDB.PressurePartType.Wye;
        }

        // Agrupa TODOS los extremos de segmento (2 por tubería) por coincidencia
        // de posición (tolerancia `tol`), produciendo UNA Juntura por sitio
        // físico distinto, con la lista COMPLETA de tuberías que llegan ahí (2,
        // 3, 4 o más) — en vez de procesar cada PAR de extremos por separado
        // (como hacía el bucle O(n²) original), que en un empalme de 3 tuberías
        // podía intentar crear hasta 3 accesorios superpuestos, cada uno
        // conectado solo a 2 de las 3.
        // `grupoCota` (opcional): etiqueta por extremo calculada por el import
        // según utilidad y cota. Dos extremos con etiquetas distintas NUNCA se
        // unen aunque coincidan en planta — son utilidades que se cruzan a
        // cotas distintas. Con etiquetas la distancia se mide en PLANTA: la
        // compatibilidad en Z ya la decidió la etiqueta, y medir en 3D separaba
        // tubos de diámetros muy distintos con la misma solera (sus ejes quedan
        // a alturas distintas).
        internal static List<Juntura> AgruparJunturas(
            List<(Point3d start, Point3d end, ObjectId id)> pipeEndpoints, double tol = 0.5,
            Dictionary<(ObjectId, int), int> grupoCota = null)
        {
            var puntos = new List<(Point3d pos, ObjectId id, int port)>();
            foreach (var pe in pipeEndpoints)
            {
                puntos.Add((pe.start, pe.id, 0));
                puntos.Add((pe.end, pe.id, 1));
            }

            var clusters = new List<Juntura>();
            var usado = new bool[puntos.Count];
            for (int i = 0; i < puntos.Count; i++)
            {
                if (usado[i]) continue;
                var j = new Juntura();
                j.Miembros.Add((puntos[i].id, puntos[i].port));
                double acumX = puntos[i].pos.X, acumY = puntos[i].pos.Y, acumZ = puntos[i].pos.Z;
                int n = 1;
                usado[i] = true;
                int? labI = null;
                if (grupoCota != null && grupoCota.TryGetValue((puntos[i].id, puntos[i].port), out int li)) labI = li;
                for (int k = i + 1; k < puntos.Count; k++)
                {
                    if (usado[k]) continue;
                    if (labI.HasValue && grupoCota.TryGetValue((puntos[k].id, puntos[k].port), out int lk)
                        && lk != labI.Value)
                        continue;                        // otra cota: no es la misma juntura
                    var c = new Point3d(acumX / n, acumY / n, acumZ / n);
                    double dist = grupoCota != null
                        ? Math.Sqrt((c.X - puntos[k].pos.X) * (c.X - puntos[k].pos.X) +
                                    (c.Y - puntos[k].pos.Y) * (c.Y - puntos[k].pos.Y))
                        : c.DistanceTo(puntos[k].pos);
                    if (dist <= tol)
                    {
                        j.Miembros.Add((puntos[k].id, puntos[k].port));
                        acumX += puntos[k].pos.X; acumY += puntos[k].pos.Y; acumZ += puntos[k].pos.Z;
                        n++;
                        usado[k] = true;
                    }
                }
                j.Ubicacion = new Point3d(acumX / n, acumY / n, acumZ / n);
                clusters.Add(j);
            }
            return clusters;
        }

        // Dado el punto de la juntura y, por cada tubo miembro, el punto de su
        // extremo LEJANO (el que no está en la juntura), decide qué 2 tubos son
        // el "paso" (los más opuestos entre sí -> puertos 0,1) y cuáles son
        // "ramal" (resto -> puertos 2,3...). Misma lógica que UNIR_VARIAS_PRESION.

        // ── Wye: identificación de puertos y orientación ─────────────────────
        // En una Wye NINGÚN par de puertos es anti-paralelo (a diferencia del
        // Tee), así que IdentificarBranchPortPorGeometria (ImportarRed.cs) no
        // sirve: ahí el "branch" se busca como el puerto cuyos otros dos son
        // colineales. Para la Y el criterio correcto es el INVERSO: el tronco
        // son los DOS puertos más opuestos entre sí (el par de mayor ángulo),
        // y el ramal es el restante.
        // Devuelve (trunkA, trunkB, branch) en índices de puerto.
        internal static (int trunkA, int trunkB, int branch) PuertosDeWye(CivilDB.PressurePart parte)
        {
            int n = parte.ConnectionCount;
            if (n != 3) return (-1, -1, -1);
            var d = new Vector3d[n];
            for (int i = 0; i < n; i++)
            {
                var v = parte.GetConnectionAt(i).Direction;
                d[i] = v.Length > 1e-9 ? v.GetNormal() : Vector3d.XAxis;
            }
            // El par de tronco = el de producto escalar MÍNIMO (más opuesto).
            int ta = 0, tb = 1; double peor = double.MaxValue;
            for (int i = 0; i < n; i++)
                for (int j = i + 1; j < n; j++)
                {
                    double dot = d[i].DotProduct(d[j]);
                    if (dot < peor) { peor = dot; ta = i; tb = j; }
                }
            int br = 3 - ta - tb;   // 0+1+2 = 3
            return (ta, tb, br);
        }

        // Mismo criterio aplicado a los TUBOS que llegan a la juntura: el par
        // más opuesto es el tronco, el restante es el ramal.
        // Devuelve índices dentro de `vectoresSalida`.
        internal static (int trunkA, int trunkB, int branch) TubosDeWye(List<Vector3d> vectoresSalida)
        {
            int n = vectoresSalida.Count;
            if (n != 3) return (-1, -1, -1);
            var d = vectoresSalida
                .Select(v => v.Length > 1e-9 ? v.GetNormal() : Vector3d.XAxis).ToList();
            int ta = 0, tb = 1; double peor = double.MaxValue;
            for (int i = 0; i < n; i++)
                for (int j = i + 1; j < n; j++)
                {
                    double dot = d[i].DotProduct(d[j]);
                    if (dot < peor) { peor = dot; ta = i; tb = j; }
                }
            int br = 3 - ta - tb;
            return (ta, tb, br);
        }

        // Orienta una Wye ya insertada para que sus puertos apunten a los tubos
        // reales, SIN mover ninguna tubería (la geometría importada del PDF es
        // la verdad; la pieza es la que cede).
        //
        // Paso 1 — giro en Z: alinea el EJE DEL TRONCO de la pieza con el eje
        //          del tronco real (bisectriz del par más opuesto de tubos).
        // Paso 2 — espejo/giro 180° sobre el eje del tronco si el ramal quedó
        //          del lado contrario al ramal real.
        //
        // Devuelve el orden de puertos (índice de tubo por cada puerto) para
        // que el llamador conecte tubo↔puerto correctamente, o null si falla.
        internal static List<int> OrientarWye(
            CivilDB.PressurePart parte, Point3d junta,
            List<Point3d> extremosLejanos, Editor ed)
        {
            try
            {
                if (parte.ConnectionCount != 3 || extremosLejanos.Count != 3) return null;

                var vt = extremosLejanos.Select(p =>
                {
                    Vector3d v = p - junta;
                    return v.Length > 1e-9 ? v.GetNormal() : Vector3d.XAxis;
                }).ToList();

                // Direcciones actuales de los 3 puertos (antes de rotar).
                var dp = new Vector3d[3];
                for (int i = 0; i < 3; i++)
                {
                    var v = parte.GetConnectionAt(i).Direction;
                    dp[i] = v.Length > 1e-9 ? v.GetNormal() : Vector3d.XAxis;
                }

                // Ajuste GLOBAL sin prejuicios sobre quién es el ramal.
                //
                // La versión anterior fijaba el ramal con TubosDeWye (par más
                // opuesto = tronco) y solo probaba 2 asignaciones. Con ángulos
                // 70/153/136 eso elegía como "tronco" el par de 153° — que tiene
                // 27° de quiebre que la pieza NO puede absorber —, así que el
                // optimizador cuadraba el tronco y sacrificaba el ramal (76° de
                // desvío, justo lo que se veía torcido en el dibujo).
                //
                // Ahora se prueban las 6 PERMUTACIONES completas puerto→tubo
                // (3 elecciones de ramal × 2 sentidos del tronco) y gana la de
                // menor error. El ramal sale de los datos, no de una suposición.
                var permutaciones = new[]
                {
                    new[] {0,1,2}, new[] {0,2,1}, new[] {1,0,2},
                    new[] {1,2,0}, new[] {2,0,1}, new[] {2,1,0},
                };

                // Error de una asignación: perm[p] = índice del tubo que va al puerto p.
                // Se pondera el PEOR puerto (max) además de la suma, para evitar
                // soluciones que cuadran dos puertos y dejan el tercero disparado.
                double ErrorDe(double ang, int[] perm, out double[] errs)
                {
                    var rot = Matrix3d.Rotation(ang, Vector3d.ZAxis, Point3d.Origin);
                    errs = new double[3];
                    double suma = 0, peor = 0;
                    for (int p = 0; p < 3; p++)
                    {
                        double e = dp[p].TransformBy(rot).GetAngleTo(vt[perm[p]]);
                        errs[p] = e;
                        suma += e;
                        if (e > peor) peor = e;
                    }
                    return suma + peor;   // penaliza el puerto peor alineado
                }

                double mejorAng = 0, mejorErr = double.MaxValue;
                int[] mejorPerm = permutaciones[0];
                foreach (var perm in permutaciones)
                {
                    for (double g = 0; g < 360.0; g += 1.0)
                    {
                        double e = ErrorDe(g * Math.PI / 180.0, perm, out _);
                        if (e < mejorErr) { mejorErr = e; mejorAng = g * Math.PI / 180.0; mejorPerm = perm; }
                    }
                }
                // Refinamiento fino alrededor del mejor ángulo.
                for (double d = -1.0; d <= 1.0; d += 0.05)
                {
                    double g = mejorAng + d * Math.PI / 180.0;
                    double e = ErrorDe(g, mejorPerm, out _);
                    if (e < mejorErr) { mejorErr = e; mejorAng = g; }
                }

                parte.TransformBy(Matrix3d.Rotation(mejorAng, Vector3d.ZAxis, junta));
                ErrorDe(mejorAng, mejorPerm, out double[] errFinal);
                ed?.WriteMessage($"\n  · [WYE-ORIENT] Giro Z {mejorAng * 180.0 / Math.PI:F1}° — desvío por puerto: " +
                    $"P0={errFinal[0] * 180.0 / Math.PI:F1}° P1={errFinal[1] * 180.0 / Math.PI:F1}° " +
                    $"P2={errFinal[2] * 180.0 / Math.PI:F1}° (máx {errFinal.Max() * 180.0 / Math.PI:F1}°).");

                // Orden puerto→tubo con la permutación ganadora.
                var orden = mejorPerm;
                return orden.ToList();
            }
            catch (Exception ex)
            {
                ed?.WriteMessage($"\n  ⚠ [WYE-ORIENT] No se pudo orientar la Y: {ex.Message}");
                return null;
            }
        }
        internal static List<int> OrdenarPuertosPorOposicion(Point3d junta, List<Point3d> extremosLejanos)
        {
            int nP = extremosLejanos.Count;
            var dir = new Vector3d[nP];
            for (int i = 0; i < nP; i++)
            {
                Vector3d v = extremosLejanos[i] - junta;
                dir[i] = v.Length > 1e-9 ? v.GetNormal() : Vector3d.XAxis;
            }
            int ra = 0, rb = 1; double mejor = double.MaxValue;
            for (int i = 0; i < nP; i++)
                for (int j = i + 1; j < nP; j++)
                {
                    double dot = dir[i].DotProduct(dir[j]);
                    if (dot < mejor) { mejor = dot; ra = i; rb = j; }
                }
            var orden = new List<int> { ra, rb };
            for (int i = 0; i < nP; i++) if (i != ra && i != rb) orden.Add(i);
            return orden;
        }

        // Ángulo de un fitting cubriendo los DOS formatos del catálogo:
        //   · Codos PushOn : "elbow-12 in-90 degree-push on-..."  → 90
        //   · Wye Steel    : "Wye 30_ BV_ AWWA C208 ..."          → 30
        // ExtraerAnguloDeDescripcion solo entiende el primero (exige °/degree),
        // así que para las Wye devolvía null → 0 y el desempate por ángulo no
        // funcionaba. Se prueba primero el formato con °/degree y, si no hay
        // match, el patrón "Wye <n>" del nombre de familia Steel.
        internal static double? ExtraerAnguloDeFitting(string desc)
        {
            var a = ExtraerAnguloDeDescripcion(desc);
            if (a.HasValue) return a;
            if (string.IsNullOrEmpty(desc)) return null;
            var m = System.Text.RegularExpressions.Regex.Match(desc,
                @"\bWye\s*(\d{1,3})",
                System.Text.RegularExpressions.RegexOptions.IgnoreCase);
            if (m.Success && double.TryParse(m.Groups[1].Value,
                System.Globalization.NumberStyles.Float,
                System.Globalization.CultureInfo.InvariantCulture, out double v))
                return v;
            return null;
        }

        // Busca el fitting del TIPO pedido cuyo diámetro (primer número en la
        // descripción) esté más cerca de `diamObjetivo`, desempatando por
        // ángulo si aplica (codos). Reemplaza a MatchFitting (ImportarRed.cs):
        // usa OrderBy/ThenBy (ESTABLE) en vez de List.Sort con comparador
        // personalizado (INESTABLE en .NET) — importa justo en el caso de
        // empate de ángulo que causaba el bug de "codo al azar".
        internal static PresStyles.PressurePartSize BuscarFittingPorTipoYDiametro(
            List<PresStyles.PressurePartSize> fittings,
            CivilDB.PressurePartType tipo, double diamObjetivo, double anguloObjetivo)
        {
            if (fittings == null) return null;
            // El ángulo importa para Elbow Y para Wye. Antes AngDiff solo se
            // calculaba para Elbow (`: 0.0`), así que entre las 116 Wye del
            // catálogo Steel el desempate era únicamente por diámetro y salía
            // una cualquiera (típicamente "Wye 30_", la primera) aunque la
            // juntura real pidiera ~60°/75°.
            bool usaAngulo = tipo == CivilDB.PressurePartType.Elbow
                          || tipo == CivilDB.PressurePartType.Wye;
            var candidatos = fittings.Where(f => f.PartType == tipo).Select(f => new
            {
                Part = f,
                Diam = ExtraerDiametroDeDescripcion(f.Description),
                AngDiff = usaAngulo
                    ? Math.Abs((ExtraerAnguloDeFitting(f.Description) ?? 0) - Math.Abs(anguloObjetivo))
                    : 0.0
            }).ToList();
            if (candidatos.Count == 0) return null;
            // Para Wye el ÁNGULO manda sobre el diámetro exacto: una Y de 60° en
            // 12" encaja mucho mejor que una de 30° en 14". Para el resto se
            // mantiene el orden histórico (diámetro primero).
            if (tipo == CivilDB.PressurePartType.Wye)
                return candidatos
                    .OrderBy(c => c.AngDiff)
                    .ThenBy(c => Math.Abs(c.Diam - diamObjetivo))
                    .First().Part;
            return candidatos
                .OrderBy(c => Math.Abs(c.Diam - diamObjetivo))
                .ThenBy(c => c.AngDiff)
                .First().Part;
        }

        // Orquestador: agrupa junturas, decide tipo+tamaño con los helpers de
        // arriba, coloca el accesorio (o conecta directo si son 2 tubos del
        // mismo diámetro sin ángulo, o si no hay pieza disponible). Reemplaza
        // al bucle pareado O(n²) de CrearRedPresionCompleta. Todo punto que
        // antes tragaba errores en silencio ahora imprime un mensaje [JUNTURA].
        internal static (int fittings, int directas, int fallidas) ProcesarJunturasPresion(
            CivilDB.PressurePipeNetwork net, Transaction tr, Editor ed,
            List<PresStyles.PressurePartSize> fittingsDisponibles,
            List<(Point3d start, Point3d end, ObjectId id)> pipeEndpoints,
            double tol = 0.5,
            Dictionary<(ObjectId, int), int> grupoCota = null)
        {
            int nFit = 0, nDirect = 0, nFail = 0;
            var junturas = AgruparJunturas(pipeEndpoints, tol, grupoCota);
            bool hayFittings = fittingsDisponibles != null && fittingsDisponibles.Count > 0;

            // Pre-scan: si alguna juntura de 3 tuberías va a pedir una Wye y la
            // PartsList no tiene ninguna, cargamos las familias Wye del catálogo
            // Imperial_AWWA_Steel (30/45/60/75/90°) UNA sola vez, y refrescamos
            // la lista de fittings. Sin esto, DecidirTeeOWye elige Wye pero
            // BuscarFittingPorTipoYDiametro devuelve null y siempre caía en Tee.
            try
            {
                bool posibleWye = false;
                int junt3 = 0;
                foreach (var jj in junturas)
                {
                    if (jj.Miembros.Count != 3) continue;
                    junt3++;
                    var vecs = jj.Miembros.Select(m =>
                    {
                        var pp = (CivilDB.PressurePipe)tr.GetObject(m.PipeId, OpenMode.ForRead);
                        Point3d far = m.Port == 0 ? pp.EndPoint : pp.StartPoint;
                        return far - jj.Ubicacion;
                    }).ToList();
                    // Log de los 3 ángulos entre pares (para diagnóstico del usuario)
                    var un = vecs.Select(v => v.Length > 1e-9 ? v.GetNormal() : Vector3d.XAxis).ToList();
                    double a01 = un[0].GetAngleTo(un[1]) * 180.0 / Math.PI;
                    double a02 = un[0].GetAngleTo(un[2]) * 180.0 / Math.PI;
                    double a12 = un[1].GetAngleTo(un[2]) * 180.0 / Math.PI;
                    var decision = DecidirTeeOWye(vecs);
                    ed.WriteMessage($"\n  · [JUNTURA-3] ({jj.Ubicacion.X:F2},{jj.Ubicacion.Y:F2}) ángulos entre salidas: {a01:F0}°, {a02:F0}°, {a12:F0}° → {decision} (umbral colinealidad ≥160°).");
                    if (decision == CivilDB.PressurePartType.Wye)
                        posibleWye = true;
                }
                if (junt3 == 0)
                    ed.WriteMessage($"\n  · [JUNTURA-WYE-SCAN] Ninguna juntura de 3 tuberías detectada — no se necesita Wye.");
                bool yaHayWye = (fittingsDisponibles ?? new List<PresStyles.PressurePartSize>())
                    .Any(f => f.PartType == CivilDB.PressurePartType.Wye);
                ed.WriteMessage($"\n  · [WYE-PRESCAN] posibleWye={posibleWye}, yaHayWye={yaHayWye}, partsListId={(net.PartsListId != ObjectId.Null ? "ok" : "NULL")}.");
                // Con las Y como sólido 3D no hace falta ninguna familia Wye de
                // catálogo: cargar las 116 del Steel en cada import solo
                // ensuciaba la lista 'Standard'.
                if (FITTING_COMO_SOLIDO && posibleWye)
                    ed.WriteMessage("\n  · [WYE-PRESCAN] Carga de Wye Steel omitida: las Y se generan como sólido 3D.");
                if (!FITTING_COMO_SOLIDO && posibleWye && !yaHayWye && net.PartsListId != ObjectId.Null)
                {
                    var pl = tr.GetObject(net.PartsListId, OpenMode.ForRead)
                             as PresStyles.PressurePartList;
                    ed.WriteMessage($"\n  · [WYE-PRESCAN] PartsList obtenida: {(pl != null ? "'" + pl.Name + "'" : "NULL cast")}.");
                    if (pl != null)
                    {
                        int nuevas = AsegurarPresionWye.AsegurarEnPartsList(
                            pl, fittingsDisponibles, tr, null, ed);
                        ed.WriteMessage($"\n  · [WYE-PRESCAN] AsegurarEnPartsList devolvió {nuevas} familia(s) nuevas.");
                        if (nuevas > 0)
                        {
                            // Refrescar la lista de fittings para incluir las Wye recién agregadas.
                            fittingsDisponibles = pl.GetParts(CivilDB.PressurePartDomainType.Fitting);
                            hayFittings = fittingsDisponibles != null && fittingsDisponibles.Count > 0;
                            ed.WriteMessage($"\n  · {nuevas} familia(s) Wye del catálogo Imperial_AWWA_Steel cargadas a la PartsList.");
                        }
                    }
                }
            }
            catch (Exception exWye)
            {
                ed?.WriteMessage($"\n  ⚠ Pre-scan Wye: {exWye.Message}");
            }

            foreach (var j in junturas)
            {
                if (j.Miembros.Count < 2) continue;   // extremo suelto, no es juntura

                if (j.Miembros.Count > 4)
                {
                    ed.WriteMessage($"\n  ⚠ [JUNTURA] {j.Miembros.Count} tuberías se encuentran en " +
                        $"({j.Ubicacion.X:F2},{j.Ubicacion.Y:F2}) — supera el máximo de 4 (Cruz) que soporta " +
                        "Civil 3D. No se crea accesorio automático aquí; únelas manualmente con UNIR_VARIAS_PRESION.");
                    nFail++;
                    continue;
                }

                var pipesInfo = j.Miembros.Select(m =>
                    (m.PipeId, m.Port, pp: (CivilDB.PressurePipe)tr.GetObject(m.PipeId, OpenMode.ForRead))).ToList();

                double d1 = 0, d2 = 0, deflex = 0;
                if (j.Miembros.Count == 2)
                {
                    d1 = pipesInfo[0].pp.NominalDiameter;
                    d2 = pipesInfo[1].pp.NominalDiameter;
                    Point3d far0 = pipesInfo[0].Port == 0 ? pipesInfo[0].pp.EndPoint : pipesInfo[0].pp.StartPoint;
                    Point3d far1 = pipesInfo[1].Port == 0 ? pipesInfo[1].pp.EndPoint : pipesInfo[1].pp.StartPoint;
                    Vector3d v1 = far0 - j.Ubicacion, v2 = far1 - j.Ubicacion;
                    deflex = 180.0 - v1.GetAngleTo(v2) * 180.0 / Math.PI;
                }

                var tipo = DecidirTipoFitting(j.Miembros.Count, d1, d2, deflex);
                // Refinamiento para 3 tuberías: discriminar Tee vs Y por los
                // ángulos entre los vectores que SALEN de la juntura. Un ángulo
                // cercano a 180° entre dos ramales = hay una recta clara → Tee.
                // Sin colinealidad = Y. Si el catálogo no tiene Y, más abajo el
                // BuscarFittingPorTipoYDiametro cae en Tee automáticamente.
                if (j.Miembros.Count == 3)
                {
                    var vecs = pipesInfo.Select(p =>
                    {
                        Point3d far = p.Port == 0 ? p.pp.EndPoint : p.pp.StartPoint;
                        return far - j.Ubicacion;
                    }).ToList();
                    var refined = DecidirTeeOWye(vecs);
                    if (refined == CivilDB.PressurePartType.Wye)
                    {
                        tipo = CivilDB.PressurePartType.Wye;
                        // Ángulo REAL del ramal respecto al tronco. `deflex` solo se
                        // calcula para 2 tubos (queda 0 con 3), así que sin esto se
                        // le pedía al catálogo una Wye de 0° y el desempate por
                        // ángulo elegía cualquiera (salía siempre "Wye 30_").
                        // Tronco = par más opuesto; el ramal es el restante. El
                        // ángulo del ramal se mide contra el EJE del tronco
                        // (dirección tubA→tubB), que es como el catálogo nombra
                        // sus Y (30/45/60/75/90°).
                        // Ángulo de ramal a pedir al catálogo. Una Wye real es
                        // "tronco casi recto + ramal desviado X°", así que el
                        // candidato correcto es la partición cuyo TRONCO sea lo
                        // más recto posible (no simplemente el par más opuesto:
                        // con 70/153/136 ese criterio tomaba el de 153°, que
                        // tiene 27° de quiebre que la pieza no puede absorber).
                        // Se prueban las 3 particiones y gana la de tronco más
                        // recto; su ángulo de ramal es el que se busca.
                        var n3 = vecs.Select(v => v.Length > 1e-9 ? v.GetNormal() : Vector3d.XAxis).ToList();
                        double mejorQuiebre = double.MaxValue, angRamalSel = 0;
                        for (int br = 0; br < 3; br++)
                        {
                            int a = (br + 1) % 3, b = (br + 2) % 3;
                            // Quiebre del tronco: 0° si los dos tubos del tronco
                            // son perfectamente opuestos (180° entre salidas).
                            double angTronco = n3[a].GetAngleTo(n3[b]) * 180.0 / Math.PI;
                            double quiebre = Math.Abs(180.0 - angTronco);
                            if (quiebre < mejorQuiebre)
                            {
                                mejorQuiebre = quiebre;
                                // Ramal medido contra el eje del tronco (a→b).
                                Vector3d eje = (n3[b] - n3[a]);
                                if (eje.Length < 1e-9) eje = n3[b];
                                eje = eje.GetNormal();
                                double ar = n3[br].GetAngleTo(eje) * 180.0 / Math.PI;
                                if (ar > 90.0) ar = 180.0 - ar;   // el catálogo usa el agudo
                                angRamalSel = ar;
                            }
                        }
                        deflex = angRamalSel;
                        ed.WriteMessage($"\n  · [JUNTURA] Y (Wye) detectada en ({j.Ubicacion.X:F2},{j.Ubicacion.Y:F2}) — " +
                            $"tronco con {mejorQuiebre:F0}° de quiebre, ramal a {angRamalSel:F0}° " +
                            $"(se buscará la Y de ese ángulo).");
                    }
                }
                // NominalDiameter viene en unidades del dibujo (pies) — confirmado con
                // datos reales: un tubo "12 in" (según su propia descripción) tiene
                // NominalDiameter=1.000. Las descripciones del catálogo ("4 in", "12
                // in"...) están en pulgadas — convertir antes de buscar, o nunca
                // encuentra nada (mismo ajuste en CorregirFittingsDeRed, RedesPresion.cs).
                double diamMaxIn = pipesInfo.Max(p => p.pp.NominalDiameter) * 12.0;

                // NOTA (2026-09-23): el catálogo Steel solo trae Wye de
                // 30/45/60/75/90°, así que una juntura de ángulo intermedio deja
                // un residuo de pocos grados repartido en los 3 puertos. Se
                // intentó generar la Y del ángulo exacto clonando la fila del
                // .sqlite, pero NO es viable: la geometría 3D de cada familia
                // vive en <catálogo>\<nombre>\DWG\<PART_FAMILY_ID>.dwg (un DWG
                // por FAMILIA, con 60 BlockReference — todos los diámetros — y
                // sin Solid3d editables). Sin ese DWG, Civil 3D falla con
                // "Fail to add a new fitting.". Se usa la Y de ángulo más
                // cercano y se avisa del desvío más abajo.
                // ── ACCESORIO COMO SÓLIDO 3D (modo de prueba, 2026-09-23) ────
                // Mientras se evalúa este camino, las Y, Tee y codos se GENERAN
                // con la geometría exacta de la juntura en vez de sacarlos del
                // catálogo (que trae pocos ángulos fijos y obligaría a crear
                // cientos de familias para cubrir cada ángulo × diámetro). El
                // flujo de catálogo sigue intacto debajo: basta poner
                // FITTING_COMO_SOLIDO=false para volver a él.
                // Dos tubos de DISTINTO diámetro que además GIRAN son un codo
                // reductor. DecidirTipoFitting los clasifica como Reducer (recto)
                // sin mirar el giro; como el Reducer no tiene versión sólida, no
                // salía ninguna pieza. Solo se corrige en el modo sólido: el
                // catálogo no tiene codos reductores.
                bool codoReductor = tipo == CivilDB.PressurePartType.Reducer
                                    && j.Miembros.Count == 2 && Math.Abs(deflex) > 1.0;
                if (FITTING_COMO_SOLIDO && codoReductor)
                    tipo = CivilDB.PressurePartType.Elbow;
                // La cruz (4 tubos) también: de catálogo salía la que hubiera en
                // la lista, a veces de otro diámetro, con salidas diminutas.
                bool tipoSolido = tipo == CivilDB.PressurePartType.Wye
                               || tipo == CivilDB.PressurePartType.Tee
                               || tipo == CivilDB.PressurePartType.Elbow
                               || tipo == CivilDB.PressurePartType.Cross;
                // Codo reductor: codo UNIFORME del diámetro mayor + reducción
                // excéntrica hacia el menor (ver ReduccionSolida.cs). El cono
                // doblado de antes no tiene equivalente comercial y dejaba las
                // bocas a desnivel de los tubos.
                if (FITTING_COMO_SOLIDO && codoReductor)
                {
                    var tubos = pipesInfo.Select(p => new WyeSolido.TuboJuntura
                    {
                        PipeId = p.PipeId, Port = p.Port,
                        Cerca = p.Port == 0 ? p.pp.StartPoint : p.pp.EndPoint,
                        Lejos = p.Port == 0 ? p.pp.EndPoint : p.pp.StartPoint,
                        DiamFt = p.pp.NominalDiameter,
                    }).OrderByDescending(t => t.DiamFt).ToList();
                    ObjectId sidRed = WyeSolido.CrearCodoConReduccion(net.Database, tr, tubos[0], tubos[1],
                        Math.Abs(deflex), SeguroMaterial(pipesInfo[0].pp), SeguroNombreRed(net), ed);
                    if (sidRed != ObjectId.Null)
                    {
                        ed.WriteMessage($"\n  · [FITTING-SOLIDO] Codo Ø{tubos[0].DiamFt * 12:F0}\" + reducción " +
                            $"{tubos[0].DiamFt * 12:F0}×{tubos[1].DiamFt * 12:F0}\" en " +
                            $"({j.Ubicacion.X:F2},{j.Ubicacion.Y:F2}), giro {Math.Abs(deflex):F0}°.");
                        nFit++;
                        continue;
                    }
                }
                if (FITTING_COMO_SOLIDO && tipoSolido)
                {
                    var brazos = pipesInfo.Select(p =>
                    {
                        Point3d far = p.Port == 0 ? p.pp.EndPoint : p.pp.StartPoint;
                        return new WyeSolido.Brazo
                        {
                            Direccion = far - j.Ubicacion,
                            // NominalDiameter viene en pies (ver nota en diamMaxIn).
                            DiamFt = p.pp.NominalDiameter,
                            PipeId = p.PipeId,
                            Port = p.Port,
                            // Cota del eje de este tubo en la juntura: la pieza se
                            // centra en el eje del tronco y cada ramal queda a la
                            // altura del suyo (bocas coaxiales).
                            EjeZ = (p.Port == 0 ? p.pp.StartPoint : p.pp.EndPoint).Z,
                        };
                    }).ToList();

                    // Ángulo característico: para 2 tubos es la deflexión del
                    // codo; para 3 es el ángulo del ramal contra el tronco.
                    // `deflex` solo se calcula con 2 tubos (queda 0 con 3), así
                    // que en Tee hay que medirlo aquí o el XDATA grababa 0°.
                    double angPieza = Math.Abs(deflex);
                    var salidas = pipesInfo
                        .Select(p => (p.Port == 0 ? p.pp.EndPoint : p.pp.StartPoint) - j.Ubicacion)
                        .ToList();
                    if (j.Miembros.Count == 3 && angPieza < 1e-6)
                        angPieza = AnguloRamalDeTres(salidas);
                    // Cruz: el ángulo característico es el que forman sus dos rectas
                    // (el menor entre salidas; 90° en una cruz ortogonal).
                    if (j.Miembros.Count == 4 && angPieza < 1e-6)
                        angPieza = salidas.SelectMany((a, ia) => salidas.Skip(ia + 1)
                            .Select(b => a.GetAngleTo(b) * 180.0 / Math.PI)).Min();

                    var info = new WyeSolido.Info
                    {
                        Tipo = tipo == CivilDB.PressurePartType.Wye ? "WYE"
                             : tipo == CivilDB.PressurePartType.Tee ? "TEE"
                             : tipo == CivilDB.PressurePartType.Cross ? "CROSS" : "ELBOW",
                        AnguloDeg = angPieza,
                        DiamPrincipalIn = diamMaxIn,
                        DiamRamalIn = pipesInfo.Min(p => p.pp.NominalDiameter) * 12.0,
                        Material = SeguroMaterial(pipesInfo[0].pp),
                        Red = SeguroNombreRed(net),
                    };

                    ObjectId sid = WyeSolido.Crear(net.Database, tr, j.Ubicacion, brazos, info, ed);
                    if (sid != ObjectId.Null)
                    {
                        ed.WriteMessage($"\n  · [FITTING-SOLIDO] {info.Tipo} generada como Solid3d en " +
                            $"({j.Ubicacion.X:F2},{j.Ubicacion.Y:F2}) — {brazos.Count} brazos, " +
                            $"Ø {string.Join("/", brazos.Select(b => (b.DiamFt * 12.0).ToString("F0") + "\""))}, " +
                            $"ángulo {info.AnguloDeg:F0}° (capa {WyeSolido.CAPA}).");
                        nFit++;
                        continue;   // sin AddFitting: la pieza ya recortó sus tubos
                    }
                    ed.WriteMessage($"\n  ⚠ [FITTING-SOLIDO] Falló la generación en " +
                        $"({j.Ubicacion.X:F2},{j.Ubicacion.Y:F2}) — se cae al catálogo.");
                }

                PresStyles.PressurePartSize pieza = (hayFittings && tipo.HasValue)
                    ? BuscarFittingPorTipoYDiametro(fittingsDisponibles, tipo.Value, diamMaxIn, deflex)
                    : null;
                if (tipo == CivilDB.PressurePartType.Wye && pieza != null)
                {
                    double angElegido = ExtraerAnguloDeFitting(pieza.Description) ?? 0;
                    ed.WriteMessage($"\n  · [JUNTURA] Y elegida: '{pieza.Description}' " +
                        $"(ángulo {angElegido:F0}° vs {deflex:F0}° pedido).");
                }
                // Fallback: si pedimos Y (Wye) pero el catálogo no tiene ninguna
                // pieza Y disponible, usar Tee en su lugar — mejor colocar algo
                // razonable que dejar la juntura sin accesorio.
                if (pieza == null && tipo == CivilDB.PressurePartType.Wye)
                {
                    pieza = BuscarFittingPorTipoYDiametro(fittingsDisponibles,
                            CivilDB.PressurePartType.Tee, diamMaxIn, deflex);
                    if (pieza != null)
                        ed.WriteMessage($"\n  · [JUNTURA] Sin Y en el catálogo — se usa Tee como fallback en ({j.Ubicacion.X:F2},{j.Ubicacion.Y:F2}).");
                }

                bool colocado = false;
                if (pieza != null)
                {
                    try
                    {
                        // La geometría de la Wye está en el catálogo Steel; hay que
                        // activarlo antes de AddFitting o lanza "Fail to add a new
                        // fitting." (los Tee/Elbow PushOn siguen resolviéndose).
                        if (pieza.PartType == CivilDB.PressurePartType.Wye)
                            AsegurarPresionWye.ActivarCatalogo(ed);
                        ObjectId fid = net.AddFitting(j.Ubicacion, pieza);
                        CivilDB.PressurePart parte = (CivilDB.PressurePart)tr.GetObject(fid, OpenMode.ForWrite);

                        List<int> orden;
                        if (j.Miembros.Count == 2) orden = new List<int> { 0, 1 };
                        else
                        {
                            var lejanos = pipesInfo.Select(p => p.Port == 0 ? p.pp.EndPoint : p.pp.StartPoint).ToList();
                            // Wye: NINGÚN par de puertos es anti-paralelo, así que el
                            // criterio "más opuestos = puertos 0/1" de
                            // OrdenarPuertosPorOposicion (pensado para Tee) deja la
                            // pieza torcida, y luego el recorte arrastra/rota el tubo.
                            // OrientarWye gira la PIEZA para que sus puertos apunten a
                            // los tubos reales y devuelve el mapeo puerto→tubo.
                            orden = (pieza.PartType == CivilDB.PressurePartType.Wye)
                                ? OrientarWye(parte, j.Ubicacion, lejanos, ed)
                                : null;
                            if (orden == null)
                                orden = OrdenarPuertosPorOposicion(j.Ubicacion, lejanos);
                        }

                        // Geometría ORIGINAL de cada tubo ANTES de conectar. ConnectToPipe
                        // reubica el extremo del tubo sobre el puerto del accesorio, y si
                        // el puerto no cae exactamente en el eje del tubo, LO ROTA. Por eso
                        // proyectar después no bastaba: para entonces el eje ya estaba
                        // deformado y la proyección se hacía sobre la recta equivocada.
                        // Guardamos (puntoFijo, direcciónOriginal) para restaurar el
                        // trazado exacto del PDF tras conectar.
                        var geomOrig = new Dictionary<ObjectId, (Point3d fijo, Vector3d dir)>();
                        foreach (var pi in pipesInfo)
                        {
                            Point3d fijoO = pi.Port == 0 ? pi.pp.EndPoint : pi.pp.StartPoint;
                            Point3d movO  = pi.Port == 0 ? pi.pp.StartPoint : pi.pp.EndPoint;
                            Vector3d dO = movO - fijoO;
                            if (dO.Length > 1e-9 && !geomOrig.ContainsKey(pi.PipeId))
                                geomOrig[pi.PipeId] = (fijoO, dO.GetNormal());
                        }

                        int conectados = 0;
                        for (int port = 0; port < orden.Count; port++)
                        {
                            int k = orden[port];
                            try { parte.ConnectToPipe(port, pipesInfo[k].PipeId, pipesInfo[k].Port); conectados++; }
                            catch (Exception ex)
                            {
                                ed.WriteMessage($"\n  ⚠ [JUNTURA] No se pudo conectar tubo al puerto {port} de " +
                                    $"'{pieza.Description}' en ({j.Ubicacion.X:F2},{j.Ubicacion.Y:F2}): {ex.Message}");
                            }
                        }

                        // Recortar cada tubo al puerto real del accesorio (igual patrón
                        // que UNIR_TUBERIAS_PRESION/UNIR_VARIAS_PRESION) para que no
                        // queden solapados/con hueco en el nudo.
                        try
                        {
                            for (int i = 0; i < parte.ConnectionCount; i++)
                            {
                                CivilDB.PressurePartConnection c = parte.GetConnectionAt(i);
                                if (c.ConnectedId == ObjectId.Null || !c.ConnectedId.IsValid) continue;
                                var pInfo = pipesInfo.FirstOrDefault(p => p.PipeId == c.ConnectedId);
                                if (pInfo.pp == null) continue;
                                var ppw = (CivilDB.PressurePipe)tr.GetObject(c.ConnectedId, OpenMode.ForWrite);
                                // La tubería NO se rota: su trazado viene del PDF y es
                                // la verdad. Solo se DESLIZA el extremo sobre su propia
                                // recta hasta el punto más cercano al puerto. Antes se
                                // asignaba c.Position directo, lo que sacaba el extremo
                                // del eje del tubo y lo dejaba girado respecto al
                                // trazado original (visible como "el tubo se tuerce
                                // para encajar con la Y").
                                // Usar la recta ORIGINAL (pre-ConnectToPipe). Si se lee el
                                // eje actual, ya viene rotado por la propia conexión y la
                                // proyección perpetúa el giro.
                                Point3d fijo; Vector3d u;
                                if (geomOrig.TryGetValue(c.ConnectedId, out var g0))
                                { fijo = g0.fijo; u = g0.dir; }
                                else
                                {
                                    fijo = (pInfo.Port == 0) ? ppw.EndPoint : ppw.StartPoint;
                                    Vector3d ejeTubo = (pInfo.Port == 0)
                                        ? (ppw.StartPoint - fijo) : (ppw.EndPoint - fijo);
                                    if (ejeTubo.Length < 1e-9) continue;
                                    u = ejeTubo.GetNormal();
                                }
                                // Proyección del puerto sobre la recta original del tubo:
                                // el extremo solo se desliza a lo largo de su propio eje.
                                double t = (c.Position - fijo).DotProduct(u);
                                Point3d destino = fijo + u * t;
                                if (pInfo.Port == 0)
                                {
                                    // Restaurar también el extremo LEJANO: ConnectToPipe
                                    // puede haberlo desplazado al re-resolver la conexión.
                                    if (ppw.EndPoint.DistanceTo(fijo) > 1e-6) ppw.EndPoint = fijo;
                                    ppw.StartPoint = destino;
                                }
                                else
                                {
                                    if (ppw.StartPoint.DistanceTo(fijo) > 1e-6) ppw.StartPoint = fijo;
                                    ppw.EndPoint = destino;
                                }
                            }
                        }
                        catch (Exception ex)
                        {
                            ed.WriteMessage($"\n  ⚠ [JUNTURA] No se pudo recortar tubos al puerto del accesorio: {ex.Message}");
                        }

                        // NO realinear la Z aquí. El accesorio nace en j.Ubicacion,
                        // que es el centroide de pipeEndpoints; quien llama es
                        // responsable de que esos endpoints YA estén a nivel de EJE
                        // antes de invocar este método (el import lo hace en
                        // ImportarRed.cs, bloque "SOLERA → EJE"). En este punto la
                        // pieza ya está CONECTADA, y escribir PressurePart.Position
                        // sobre una pieza conectada hace que Civil 3D re-resuelva la
                        // conexión y arrastre los tubos con ella: el desfase relativo
                        // codo-tubo no se corrige y encima se mueve el tubo.
                        // (Antes había un AlinearFittingAEjeTubo(parte, tr) acá; era
                        // un no-op cuando los tubos estaban a solera, y en cuanto se
                        // arregló el orden pasó a ser una escritura innecesaria.)

                        if (conectados < orden.Count)
                            ed.WriteMessage($"\n  ⚠ [JUNTURA] '{pieza.Description}' colocado pero solo " +
                                $"{conectados}/{orden.Count} tuberías conectadas.");
                        nFit++;
                        colocado = true;
                    }
                    catch (Exception ex)
                    {
                        ed.WriteMessage($"\n  ⚠ [JUNTURA] Falló al crear/colocar '{pieza.Description}' en " +
                            $"({j.Ubicacion.X:F2},{j.Ubicacion.Y:F2}): {ex.Message}. Se intenta conexión directa.");
                        try
                        {
                            ed.WriteMessage($"\n     [JUNTURA-DBG] PartType={pieza.PartType}, FamilyGuid={pieza.FamilyGuid}, PartSizeGuid={pieza.PartSizeGuid}");
                        }
                        catch { }
                    }
                }
                else if (tipo.HasValue && tipo.Value != CivilDB.PressurePartType.Coupling)
                {
                    ed.WriteMessage($"\n  ⚠ [JUNTURA] No hay {tipo.Value} en la Parts List para Ø{diamMaxIn:F0}" +
                        (j.Miembros.Count == 2 && Math.Abs(deflex) > 1.0 ? $" {deflex:F0}°" : "") +
                        $" en ({j.Ubicacion.X:F2},{j.Ubicacion.Y:F2})." +
                        (j.Miembros.Count > 2 ? " Esas tuberías quedan SIN conectar (no hay conexión directa posible para 3+ tubos)." : " Se conecta directo."));
                }

                if (colocado) continue;

                // Fallback: conexión directa tubo-a-tubo, solo tiene sentido para 2 miembros.
                if (j.Miembros.Count == 2)
                {
                    try
                    {
                        var ppw = (CivilDB.PressurePipe)tr.GetObject(pipesInfo[0].PipeId, OpenMode.ForWrite);
                        ppw.ConnectToPipe(pipesInfo[0].Port, pipesInfo[1].PipeId, pipesInfo[1].Port);
                        nDirect++;
                    }
                    catch (Exception ex)
                    {
                        ed.WriteMessage($"\n  ⚠ [JUNTURA] Conexión directa falló en " +
                            $"({j.Ubicacion.X:F2},{j.Ubicacion.Y:F2}): {ex.Message}");
                        nFail++;
                    }
                }
                else nFail++;
            }
            return (nFit, nDirect, nFail);
        }
    }
}
