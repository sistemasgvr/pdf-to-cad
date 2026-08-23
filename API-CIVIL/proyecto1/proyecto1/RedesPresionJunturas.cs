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

        // Agrupa TODOS los extremos de segmento (2 por tubería) por coincidencia
        // de posición (tolerancia `tol`), produciendo UNA Juntura por sitio
        // físico distinto, con la lista COMPLETA de tuberías que llegan ahí (2,
        // 3, 4 o más) — en vez de procesar cada PAR de extremos por separado
        // (como hacía el bucle O(n²) original), que en un empalme de 3 tuberías
        // podía intentar crear hasta 3 accesorios superpuestos, cada uno
        // conectado solo a 2 de las 3.
        internal static List<Juntura> AgruparJunturas(
            List<(Point3d start, Point3d end, ObjectId id)> pipeEndpoints, double tol = 0.5)
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
                // Comparar contra el CENTROIDE del cluster en curso (no solo el
                // primer punto) para que la tolerancia sea consistente aunque el
                // cluster crezca con más de 2 miembros.
                for (int k = i + 1; k < puntos.Count; k++)
                {
                    if (usado[k]) continue;
                    var c = new Point3d(acumX / n, acumY / n, acumZ / n);
                    if (c.DistanceTo(puntos[k].pos) <= tol)
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
            var candidatos = fittings.Where(f => f.PartType == tipo).Select(f => new
            {
                Part = f,
                Diam = ExtraerDiametroDeDescripcion(f.Description),
                AngDiff = tipo == CivilDB.PressurePartType.Elbow
                    ? Math.Abs((ExtraerAnguloDeDescripcion(f.Description) ?? 0) - Math.Abs(anguloObjetivo))
                    : 0.0
            }).ToList();
            if (candidatos.Count == 0) return null;
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
            double tol = 0.5)
        {
            int nFit = 0, nDirect = 0, nFail = 0;
            var junturas = AgruparJunturas(pipeEndpoints, tol);
            bool hayFittings = fittingsDisponibles != null && fittingsDisponibles.Count > 0;

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
                // NominalDiameter viene en unidades del dibujo (pies) — confirmado con
                // datos reales: un tubo "12 in" (según su propia descripción) tiene
                // NominalDiameter=1.000. Las descripciones del catálogo ("4 in", "12
                // in"...) están en pulgadas — convertir antes de buscar, o nunca
                // encuentra nada (mismo ajuste en CorregirFittingsDeRed, RedesPresion.cs).
                double diamMaxIn = pipesInfo.Max(p => p.pp.NominalDiameter) * 12.0;

                PresStyles.PressurePartSize pieza = (hayFittings && tipo.HasValue)
                    ? BuscarFittingPorTipoYDiametro(fittingsDisponibles, tipo.Value, diamMaxIn, deflex)
                    : null;

                bool colocado = false;
                if (pieza != null)
                {
                    try
                    {
                        ObjectId fid = net.AddFitting(j.Ubicacion, pieza);
                        CivilDB.PressurePart parte = (CivilDB.PressurePart)tr.GetObject(fid, OpenMode.ForWrite);

                        List<int> orden;
                        if (j.Miembros.Count == 2) orden = new List<int> { 0, 1 };
                        else
                        {
                            var lejanos = pipesInfo.Select(p => p.Port == 0 ? p.pp.EndPoint : p.pp.StartPoint).ToList();
                            orden = OrdenarPuertosPorOposicion(j.Ubicacion, lejanos);
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
                                if (pInfo.Port == 0) ppw.StartPoint = c.Position; else ppw.EndPoint = c.Position;
                            }
                        }
                        catch (Exception ex)
                        {
                            ed.WriteMessage($"\n  ⚠ [JUNTURA] No se pudo recortar tubos al puerto del accesorio: {ex.Message}");
                        }

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
