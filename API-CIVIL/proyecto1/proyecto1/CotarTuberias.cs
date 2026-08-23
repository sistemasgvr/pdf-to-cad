using System;
using System.Collections.Generic;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.EditorInput;
using Autodesk.AutoCAD.Geometry;
using Autodesk.AutoCAD.Runtime;
using Autodesk.Civil.ApplicationServices;
using CivilDB = Autodesk.Civil.DatabaseServices;
using Exception = System.Exception;

// ============================================================================
//  COTAR_TUBERIAS ("Agregar etiquetas") — genera 3 tipos de anotación, cada
//  una en su propia capa:
//
//   1) ETIQUETAS_TUBERIAS: por cada EXTREMO de tubería (gravedad/conduit/
//      presión), un MLeader con "INICIO TUBERIA <nombre>" o "DESCARGA TUBERIA
//      <nombre>" (el extremo de MENOR cota es siempre "descarga", sin importar
//      cuál llama Civil3D Start/End — así se valida que el sentido sea
//      consistente con flujo por gravedad), "PROG: 0+00.00" (estación sobre
//      el eje de la red, si existe) y "COTA: valor". La flecha ancla en el
//      borde real de la estructura conectada (rectángulo o círculo).
//
//   2) ETIQUETAS_BUZONES: por cada BUZÓN (gravedad/conduit), un MLeader al
//      CENTRO del buzón con "BUZÓN <nombre>", "CT: rim", "CF: sump",
//      "H: <Structure.Height — Altura de estructura real de Civil3D>".
//
//   3) ETIQUETAS_PENDIENTES: por cada tubería de gravedad/conduit, una flecha
//      corta paralela a la mitad de la tubería (separada por un pequeño
//      espacio) que apunta hacia el extremo de MENOR cota (sentido real del
//      flujo), y junto a ella la pendiente "S=x.xx%".
//
//   El tamaño de texto/flecha/offset es UNA sola escala global (promedio del
//   diámetro de TODAS las tuberías del dibujo), no por elemento — si se
//   calculara por tubería, una tubería grande generaba etiquetas gigantes
//   mezcladas con las normales (caótico). Con una escala global el resultado
//   es uniforme sin importar qué tan grande sea cada tubería/estructura.
// ============================================================================

namespace Civil3DBasico
{
    public class ComandosCotarTuberias
    {
        private const string CapaBuzones = "ETIQUETAS_BUZONES";
        private const string CapaTuberias = "ETIQUETAS_TUBERIAS";
        private const string CapaPendientes = "ETIQUETAS_PENDIENTES";

        [CommandMethod("COTAR_TUBERIAS")]
        public void CotarTuberias()
        {
            Document doc = Application.DocumentManager.MdiActiveDocument;
            if (doc == null) return;
            Editor ed = doc.Editor;
            Database db = doc.Database;
            CivilDocument civilDoc = CivilApplication.ActiveDocument;

            ed.WriteMessage("\n═══ AGREGAR ETIQUETAS — tuberías, buzones y sentido de flujo ═══");

            using (Transaction tr = db.TransactionManager.StartTransaction())
            {
                try
                {
                    AsegurarCapas(db, tr);
                    BlockTable bt = tr.GetObject(db.BlockTableId, OpenMode.ForRead) as BlockTable;
                    BlockTableRecord ms = tr.GetObject(bt[BlockTableRecord.ModelSpace], OpenMode.ForWrite) as BlockTableRecord;

                    ObjectIdCollection nets = civilDoc.GetPipeNetworkIds();
                    ObjectIdCollection presNets = civilDoc.GetPressurePipeNetworkIds();

                    // ── Escala GLOBAL única (promedio de diámetro de TODAS las tuberías del
                    //    dibujo) — no por elemento, para que el tamaño de texto/flecha sea
                    //    uniforme sin importar qué tan grande sea cada tubería/estructura. ──
                    double sumDia = 0.0; int nDia = 0;
                    foreach (ObjectId nid in nets)
                    {
                        CivilDB.Network n2 = tr.GetObject(nid, OpenMode.ForRead) as CivilDB.Network;
                        if (n2 == null) continue;
                        foreach (ObjectId pid in n2.GetPipeIds())
                        {
                            CivilDB.Pipe p2 = tr.GetObject(pid, OpenMode.ForRead) as CivilDB.Pipe;
                            if (p2 == null) continue;
                            try { sumDia += p2.InnerDiameterOrWidth; nDia++; } catch { }
                        }
                    }
                    foreach (ObjectId nid in presNets)
                    {
                        CivilDB.PressurePipeNetwork n2 = tr.GetObject(nid, OpenMode.ForRead) as CivilDB.PressurePipeNetwork;
                        if (n2 == null) continue;
                        foreach (ObjectId pid in n2.GetPipeIds())
                        {
                            CivilDB.PressurePipe p2 = tr.GetObject(pid, OpenMode.ForRead) as CivilDB.PressurePipe;
                            if (p2 == null) continue;
                            // PressurePipe.NominalDiameter ya viene en unidades del
                            // dibujo (pies) — no en pulgadas, confirmado con datos
                            // reales (ver el mismo fix en ImportarRed.cs).
                            try { sumDia += p2.NominalDiameter; nDia++; } catch { }
                        }
                    }
                    double diaMedio = nDia > 0 ? sumDia / nDia : 1.0;
                    if (diaMedio < 0.1) diaMedio = 1.0;

                    double txtH = diaMedio * 0.45;   // mitad del tamaño anterior (que era diaMedio*0.9)
                    double off = diaMedio * 3.0;      // leader largo, evita cruces entre etiquetas cercanas

                    int nRedes = 0, nTubos = 0, nBuzones = 0, nEtiquetas = 0, nFlechas = 0;

                    // Etiquetas de tubería: se acumulan aquí y se dibujan todas al final
                    // (agrupadas por estructura conectada) — ver DibujarEtiquetasTuberiaAgrupadas.
                    var etiquetasTuberia = new List<(Point3d punto, List<string> lineas, ObjectId structId)>();

                    // ── Redes de gravedad y conduit (mismo tipo Network) ──
                    foreach (ObjectId nid in nets)
                    {
                        CivilDB.Network net = tr.GetObject(nid, OpenMode.ForRead) as CivilDB.Network;
                        if (net == null) continue;
                        nRedes++;

                        CivilDB.Alignment alignRed = null;
                        try
                        {
                            ObjectId alignId = net.ReferenceAlignmentId;
                            if (!alignId.IsNull && alignId.IsValid)
                                alignRed = tr.GetObject(alignId, OpenMode.ForRead) as CivilDB.Alignment;
                        }
                        catch { }

                        foreach (ObjectId pid in net.GetPipeIds())
                        {
                            try
                            {
                                CivilDB.Pipe p = tr.GetObject(pid, OpenMode.ForRead) as CivilDB.Pipe;
                                if (p == null) continue;
                                nTubos++;

                                double invStart = InvertEnNodo(p.StartStructureId, p.StartPoint, p, tr);
                                double invEnd = InvertEnNodo(p.EndStructureId, p.EndPoint, p, tr);
                                // El extremo de MAYOR cota es "inicio" (aguas arriba) — no se
                                // asume que Start=aguas arriba, se valida contra la elevación real.
                                bool startEsInicio = invStart >= invEnd;

                                Point3d ptStart = PuntoVisualExtremo(p.StartStructureId, p.StartPoint, p.EndPoint, tr);
                                Point3d ptEnd = PuntoVisualExtremo(p.EndStructureId, p.EndPoint, p.StartPoint, tr);

                                string nombrePipe; try { nombrePipe = p.Name; } catch { nombrePipe = "?"; }

                                var lineasStart = new List<string>
                                {
                                    (startEsInicio ? "INICIO " : "DESCARGA ") + nombrePipe
                                };
                                string progStart = EstacionTexto(alignRed, p.StartPoint);
                                if (progStart != null) lineasStart.Add("PROG: " + progStart);
                                lineasStart.Add("COTA: " + invStart.ToString("F2"));

                                var lineasEnd = new List<string>
                                {
                                    (startEsInicio ? "DESCARGA " : "INICIO ") + nombrePipe
                                };
                                string progEnd = EstacionTexto(alignRed, p.EndPoint);
                                if (progEnd != null) lineasEnd.Add("PROG: " + progEnd);
                                lineasEnd.Add("COTA: " + invEnd.ToString("F2"));

                                etiquetasTuberia.Add((ptStart, lineasStart, p.StartStructureId));
                                etiquetasTuberia.Add((ptEnd, lineasEnd, p.EndStructureId));
                                nEtiquetas += 2;

                                double diamReal = 0.0;
                                try { diamReal = p.OuterDiameterOrWidth; } catch { }
                                if (diamReal < 0.05) { try { diamReal = p.InnerDiameterOrWidth; } catch { } }
                                if (diamReal < 0.05) diamReal = diaMedio;
                                // La pendiente mostrada es la propiedad real "Talud de tubería
                                // (extremo inicial)" de Civil3D (Pipe.Slope, ya usada en el resto
                                // del proyecto — es un ratio, ×100 para %), no un cálculo geométrico
                                // aparte que podría no coincidir con lo que Civil3D reporta.
                                double? slopePipe = null;
                                try { slopePipe = p.Slope; } catch { }
                                DibujarFlechaFlujo(ms, tr, p.StartPoint, p.EndPoint, invStart, invEnd, diaMedio, txtH, diamReal, slopePipe);
                                nFlechas++;
                            }
                            catch { }
                        }

                        foreach (ObjectId sid in net.GetStructureIds())
                        {
                            try
                            {
                                CivilDB.Structure st = tr.GetObject(sid, OpenMode.ForRead) as CivilDB.Structure;
                                if (st == null) continue;
                                string nombre; try { nombre = st.Name; } catch { nombre = "?"; }

                                double ct; try { ct = st.RimElevation; } catch { continue; }
                                double cf; try { cf = st.SumpElevation; } catch { continue; }
                                Point3d centro; try { centro = st.Location; } catch { continue; }

                                // "Altura de estructura" real de Civil3D (Structure.Height), no
                                // CT−CF a mano — puede incluir espesor de piso u otras piezas
                                // que la resta simple no contempla. Si no se puede leer, se cae
                                // al cálculo simple como aproximación razonable.
                                double altura;
                                try { altura = st.Height; } catch { altura = ct - cf; }

                                var lineas = new List<string>
                                {
                                    "BUZÓN " + nombre,
                                    $"CT: {ct:F2}",
                                    $"CF: {cf:F2}",
                                    $"H: {altura:F2}",
                                };
                                DibujarEtiquetaBuzon(ms, tr, CapaBuzones, centro, lineas, txtH, off);
                                nBuzones++;
                                nEtiquetas++;
                            }
                            catch { }
                        }
                    }

                    // ── Redes de presión (agua/gas): mismo formato de etiqueta, pero neutro
                    //    (sin "INICIO/DESCARGA" — el sentido en presión no lo define la
                    //    gravedad) y sin buzones. Sí llevan flecha + "S=x.xx%" (usa
                    //    PressurePipe.Slope, la misma propiedad real que en gravedad). ──
                    foreach (ObjectId nid in presNets)
                    {
                        CivilDB.PressurePipeNetwork net = tr.GetObject(nid, OpenMode.ForRead) as CivilDB.PressurePipeNetwork;
                        if (net == null) continue;
                        nRedes++;

                        foreach (ObjectId pid in net.GetPipeIds())
                        {
                            try
                            {
                                CivilDB.PressurePipe p = tr.GetObject(pid, OpenMode.ForRead) as CivilDB.PressurePipe;
                                if (p == null) continue;
                                nTubos++;

                                // NominalDiameter ya viene en pies (unidades del dibujo).
                                double r = 0.0; try { r = p.NominalDiameter / 2.0; } catch { }
                                double sInv = p.StartPoint.Z - r;
                                double eInv = p.EndPoint.Z - r;

                                string nombrePipe; try { nombrePipe = p.Name; } catch { nombrePipe = "?"; }
                                CivilDB.Alignment alignPipe = null;
                                try
                                {
                                    ObjectId alignId = p.ReferenceAlignmentId;
                                    if (!alignId.IsNull && alignId.IsValid)
                                        alignPipe = tr.GetObject(alignId, OpenMode.ForRead) as CivilDB.Alignment;
                                }
                                catch { }

                                var lineasStart = new List<string> { "TUBERIA " + nombrePipe };
                                string progStart = EstacionTexto(alignPipe, p.StartPoint);
                                if (progStart != null) lineasStart.Add("PROG: " + progStart);
                                lineasStart.Add("COTA: " + sInv.ToString("F2"));

                                var lineasEnd = new List<string> { "TUBERIA " + nombrePipe };
                                string progEnd = EstacionTexto(alignPipe, p.EndPoint);
                                if (progEnd != null) lineasEnd.Add("PROG: " + progEnd);
                                lineasEnd.Add("COTA: " + eInv.ToString("F2"));

                                etiquetasTuberia.Add((p.StartPoint, lineasStart, ObjectId.Null));
                                etiquetasTuberia.Add((p.EndPoint, lineasEnd, ObjectId.Null));
                                nEtiquetas += 2;

                                // OuterDiameter ya viene en pies (unidades del dibujo).
                                double diamRealPres = 0.0;
                                try { diamRealPres = p.OuterDiameter; } catch { }
                                if (diamRealPres < 0.05) diamRealPres = r * 2.0;
                                if (diamRealPres < 0.05) diamRealPres = diaMedio;
                                double? slopePres = null;
                                try { slopePres = p.Slope; } catch { }
                                DibujarFlechaFlujo(ms, tr, p.StartPoint, p.EndPoint, sInv, eInv, diaMedio, txtH, diamRealPres, slopePres);
                                nFlechas++;
                            }
                            catch { }
                        }
                    }

                    // Se dibujan al final, agrupadas por la ESTRUCTURA a la que conecta cada
                    // extremo: si dos o más tuberías comparten un mismo buzón (el caso más
                    // común — cada nodo intermedio de una red es la descarga de una tubería Y
                    // el inicio de la siguiente), sus etiquetas se escalonan en la misma
                    // dirección fija en vez de quedar exactamente montadas una sobre otra.
                    DibujarEtiquetasTuberiaAgrupadas(ms, tr, etiquetasTuberia, txtH, off);

                    tr.Commit();
                    ed.WriteMessage($"\n✓ Redes: {nRedes}  ·  Tuberías: {nTubos}  ·  Buzones: {nBuzones}  ·  " +
                                     $"Etiquetas: {nEtiquetas}  ·  Flechas de flujo: {nFlechas}");
                    ed.WriteMessage($"\n  Capas: {CapaTuberias} (verde) · {CapaBuzones} (cian) · {CapaPendientes} (amarillo).");
                }
                catch (Exception ex)
                {
                    ed.WriteMessage($"\n✗ Error: {ex.Message}");
                    tr.Abort();
                }
            }
        }

        // "Elevación de rasante inicial/final" real de Civil3D en un extremo de
        // tubería = eje de la tubería en ese extremo MENOS el radio interior
        // (centerline.Z − r) — SIEMPRE calculado desde la propia tubería, nunca
        // desde el buzón conectado (structId/tr quedan sin usar a propósito).
        //
        // ANTES se leía Structure.SumpElevation del buzón conectado cuando había
        // uno. Esa dependencia fue la causa de varios bugs de cota (offsets de
        // -0.5/-0.833 pies, INICIO/DESCARGA con el valor equivocado) cuando el
        // Sump del buzón no estaba perfectamente sincronizado con la tubería —
        // la rasante de la PROPIA tubería no depende de ninguna otra entidad y
        // nunca fallaba.
        internal static double InvertEnNodo(ObjectId structId, Point3d centerline, CivilDB.Pipe p, Transaction tr)
        {
            double r = 0.0;
            try { double h = p.InnerHeight; if (h > 1e-6) r = h / 2.0; } catch { }
            if (r <= 0.0) { try { r = p.InnerDiameterOrWidth / 2.0; } catch { } }
            return centerline.Z - r;
        }

        // p.StartPoint/EndPoint quedan en el CENTRO de la estructura conectada (así conecta
        // la topología de red en Civil3D), pero visualmente la tubería "termina" en el borde
        // de esa estructura. Se calcula dónde el rayo tubería→otro extremo SALE del
        // rectángulo real (GeometricExtents) — no se asume una forma circular.
        internal static Point3d PuntoVisualExtremo(ObjectId structId, Point3d propio, Point3d otro, Transaction tr)
        {
            if (structId.IsNull || !structId.IsValid) return propio;
            try
            {
                var st = tr.GetObject(structId, OpenMode.ForRead) as CivilDB.Structure;
                if (st == null) return propio;

                Extents3d ext = st.GeometricExtents;
                Vector3d dirRaw = otro - propio;
                if (dirRaw.Length < 1e-6) return propio;
                Vector3d dir = dirRaw.GetNormal();

                double dist = DistanciaHastaBordeRectangulo(propio, dir, ext.MinPoint, ext.MaxPoint);
                if (double.IsNaN(dist) || dist <= 0.0) return propio;
                return propio + dir * dist;
            }
            catch { return propio; }
        }

        // Distancia desde "origen" (dentro del rectángulo) hasta donde el rayo UNITARIO
        // "dir" sale del rectángulo [min,max]. Método de las franjas (slab method) en 2D,
        // ignora Z — el buzón se dibuja en planta.
        static double DistanciaHastaBordeRectangulo(Point3d origen, Vector3d dir, Point3d min, Point3d max)
        {
            double tx = dir.X > 1e-9 ? (max.X - origen.X) / dir.X
                      : dir.X < -1e-9 ? (min.X - origen.X) / dir.X
                      : double.PositiveInfinity;
            double ty = dir.Y > 1e-9 ? (max.Y - origen.Y) / dir.Y
                      : dir.Y < -1e-9 ? (min.Y - origen.Y) / dir.Y
                      : double.PositiveInfinity;
            double dist = Math.Min(tx, ty);
            if (double.IsInfinity(dist) || dist <= 0.0) return double.NaN;
            return dist;
        }

        // "0+81.45", misma convención que usa Civil3D nativamente para estaciones.
        // Devuelve null si no hay eje o el punto no se puede proyectar (no se inventa).
        static string EstacionTexto(CivilDB.Alignment align, Point3d pt)
        {
            if (align == null) return null;
            try
            {
                double sta = 0.0, off = 0.0;
                align.StationOffset(pt.X, pt.Y, ref sta, ref off);
                int whole = (int)Math.Floor(sta / 100.0);
                double rem = sta - whole * 100.0;
                return $"{whole}+{rem:00.00}";
            }
            catch { return null; }
        }

        // Dirección FIJA de las etiquetas de tubería: siempre hacia la derecha, con un
        // leve descenso (para que el "landing" de la MLeader quede un poco hacia abajo
        // antes de virar horizontal hacia el texto) — nunca varía según el ángulo de la
        // tubería, así todas las etiquetas de tubería quedan del mismo lado, siempre.
        static readonly Vector3d DirEtiquetaTuberia = new Vector3d(1.0, -0.35, 0.0).GetNormal();

        // MLeader con texto multilínea (una línea por elemento de "lineas"). La flecha
        // va en "punto" y la cola, SIEMPRE hacia la derecha (DirEtiquetaTuberia) — así
        // todas las etiquetas de tubería quedan consistentemente del mismo lado.
        static void DibujarEtiqueta(BlockTableRecord ms, Transaction tr, string capa, Point3d punto,
            List<string> lineas, double txtH, double off)
        {
            Point3d flecha = new Point3d(punto.X, punto.Y, 0.0);
            Point3d cola = new Point3d(flecha.X + DirEtiquetaTuberia.X * off, flecha.Y + DirEtiquetaTuberia.Y * off, 0.0);

            MLeader ml = new MLeader();
            ml.SetDatabaseDefaults();
            ml.Layer = capa;
            ml.ContentType = ContentType.MTextContent;
            try { ml.TextHeight = txtH; } catch { }
            try { ml.ArrowSize = txtH * 0.6; } catch { }
            try { ml.DoglegLength = txtH * 1.5; } catch { }
            try { ml.LandingGap = txtH * 0.4; } catch { }
            try { ml.EnableLanding = true; } catch { }

            MText mt = new MText();
            mt.SetDatabaseDefaults();
            mt.Contents = string.Join("\\P", lineas);
            mt.TextHeight = txtH;
            mt.Location = cola;
            // MiddleLeft → el texto crece hacia la DERECHA de la cola.
            mt.Attachment = AttachmentPoint.MiddleLeft;
            ml.MText = mt;

            ml.AddLeaderLine(flecha);
            ms.AppendEntity(ml);
            tr.AddNewlyCreatedDBObject(ml, true);
        }

        // Dibuja TODAS las etiquetas de tubería acumuladas, agrupadas por la estructura a
        // la que conecta cada extremo (no por proximidad de punto: dos extremos del mismo
        // buzón pueden caer en bordes distintos del rectángulo, pero siguen siendo el
        // mismo nodo). Dentro de un grupo con más de una etiqueta, cada una se dibuja más
        // lejos que la anterior (misma dirección fija hacia la derecha) para no montarse.
        // Los extremos sueltos (sin estructura, ObjectId.Null) nunca se agrupan entre sí.
        static void DibujarEtiquetasTuberiaAgrupadas(BlockTableRecord ms, Transaction tr,
            List<(Point3d punto, List<string> lineas, ObjectId structId)> etiquetas, double txtH, double offBase)
        {
            var grupos = new Dictionary<string, List<int>>();
            for (int i = 0; i < etiquetas.Count; i++)
            {
                ObjectId sid = etiquetas[i].structId;
                string key = (!sid.IsNull && sid.IsValid) ? "S" + sid.Handle : "P" + i;
                if (!grupos.TryGetValue(key, out var lista)) { lista = new List<int>(); grupos[key] = lista; }
                lista.Add(i);
            }

            foreach (var lista in grupos.Values)
            {
                double offActual = offBase;
                foreach (int i in lista)
                {
                    var e = etiquetas[i];
                    DibujarEtiqueta(ms, tr, CapaTuberias, e.punto, e.lineas, txtH, offActual);
                    offActual += txtH * 5.5;   // suficiente para no pisar el bloque de texto anterior
                }
            }
        }

        // Etiqueta de buzón: leader de DOS tramos — uno EMPINADO (≥70° respecto a la
        // horizontal) que sale del buzón, y uno horizontal hacia la izquierda que llega
        // al texto (que también queda a la izquierda). Un solo tramo recto casi horizontal
        // se veía "raro" (ángulo demasiado chico) — con el tramo empinado se ve como un
        // leader normal de dibujo técnico.
        static void DibujarEtiquetaBuzon(BlockTableRecord ms, Transaction tr, string capa, Point3d punto,
            List<string> lineas, double txtH, double off)
        {
            Point3d flecha = new Point3d(punto.X, punto.Y, 0.0);

            Vector3d dirEmpinada = new Vector3d(-0.26, -0.966, 0.0).GetNormal();   // ≈75° desde la horizontal
            Vector3d dirHorizontal = new Vector3d(-1.0, 0.0, 0.0);

            double distEmpinada = off * 0.45;
            double distHorizontal = off * 0.55;

            Point3d bend = flecha + dirEmpinada * distEmpinada;
            Point3d cola = bend + dirHorizontal * distHorizontal;

            MLeader ml = new MLeader();
            ml.SetDatabaseDefaults();
            ml.Layer = capa;
            ml.ContentType = ContentType.MTextContent;
            try { ml.TextHeight = txtH; } catch { }
            try { ml.ArrowSize = txtH * 0.6; } catch { }
            try { ml.DoglegLength = txtH * 1.5; } catch { }
            try { ml.LandingGap = txtH * 0.4; } catch { }
            try { ml.EnableLanding = true; } catch { }

            MText mt = new MText();
            mt.SetDatabaseDefaults();
            mt.Contents = string.Join("\\P", lineas);
            mt.TextHeight = txtH;
            mt.Location = cola;
            // MiddleRight → el texto crece hacia la IZQUIERDA de la cola.
            mt.Attachment = AttachmentPoint.MiddleRight;
            ml.MText = mt;

            int idx = ml.AddLeaderLine(flecha);
            ml.AddLastVertex(idx, bend);

            ms.AppendEntity(ml);
            tr.AddNewlyCreatedDBObject(ml, true);
        }

        // Separación mínima entre la flecha/pendiente y el borde exterior real de la
        // tubería, para que nunca queden superpuestas sobre tuberías gruesas.
        private const double SeparacionBordeTuberia = 0.5;   // pies

        // Flecha corta paralela a la tubería (desplazada un pequeño espacio a un
        // costado), apuntando hacia el extremo de MENOR cota (sentido real de flujo
        // por gravedad), con la pendiente "S=x.xx%" junto a ella, en el mismo ángulo.
        // "escala"/"txtH" son la escala GLOBAL única del comando (tamaño uniforme);
        // "diametroReal" es el diámetro de ESTA tubería en particular, usado solo para
        // calcular la separación mínima al borde exterior (0.5 ft) — así una tubería
        // gruesa no queda con la flecha/texto encima.
        static void DibujarFlechaFlujo(BlockTableRecord ms, Transaction tr,
            Point3d p1, Point3d p2, double invP1, double invP2, double escala, double txtH, double diametroReal,
            double? slopePipe)
        {
            Vector3d dirPipe = new Vector3d(p2.X - p1.X, p2.Y - p1.Y, 0.0);
            if (dirPipe.Length < 1e-6) return;
            dirPipe = dirPipe.GetNormal();
            Vector3d perp = new Vector3d(-dirPipe.Y, dirPipe.X, 0.0);

            double largoFlecha = escala * 2.0;
            double gap = diametroReal / 2.0 + SeparacionBordeTuberia;

            Point3d mid = new Point3d((p1.X + p2.X) / 2.0, (p1.Y + p2.Y) / 2.0, 0.0);
            // Apunta hacia el extremo con MENOR cota — si p1 es más bajo, el flujo va
            // en sentido contrario a dirPipe (que va de p1 a p2).
            Vector3d dirFlujo = invP1 <= invP2 ? -dirPipe : dirPipe;

            Point3d centro = mid + perp * gap;
            Point3d cola = centro - dirFlujo * (largoFlecha / 2.0);
            Point3d cabeza = centro + dirFlujo * (largoFlecha / 2.0);

            DrawLineaSimple(ms, tr, cola, cabeza);

            double alaLen = largoFlecha * 0.4;
            double angRad = 25.0 * Math.PI / 180.0;
            Vector3d back = -dirFlujo;
            Vector3d alaA = back.RotateBy(angRad, Vector3d.ZAxis);
            Vector3d alaB = back.RotateBy(-angRad, Vector3d.ZAxis);
            DrawLineaSimple(ms, tr, cabeza, cabeza + alaA * alaLen);
            DrawLineaSimple(ms, tr, cabeza, cabeza + alaB * alaLen);

            // Pendiente real de Civil3D (Pipe.Slope, "Talud de tubería (extremo inicial)")
            // en vez del cálculo geométrico eje-a-eje — si por algo no se pudo leer, se
            // cae al cálculo geométrico como respaldo.
            double pendiente;
            if (slopePipe.HasValue)
            {
                pendiente = Math.Abs(slopePipe.Value) * 100.0;
            }
            else
            {
                double longitudPipe = p1.DistanceTo(p2);
                pendiente = longitudPipe > 1e-6 ? Math.Abs(invP1 - invP2) / longitudPipe * 100.0 : 0.0;
            }

            double rot = Math.Atan2(dirPipe.Y, dirPipe.X);
            if (rot > Math.PI / 2.0 + 1e-6 || rot < -Math.PI / 2.0 - 1e-6) rot += Math.PI;   // nunca "boca abajo"

            Point3d posTexto = mid + perp * (gap + escala * 1.0);
            var mt = new MText();
            mt.SetDatabaseDefaults();
            mt.Layer = CapaPendientes;
            mt.Contents = $"S={pendiente:F2}%";
            mt.TextHeight = txtH;
            mt.Location = posTexto;
            mt.Attachment = AttachmentPoint.MiddleCenter;
            try { mt.Rotation = rot; } catch { }
            ms.AppendEntity(mt); tr.AddNewlyCreatedDBObject(mt, true);
        }

        static void DrawLineaSimple(BlockTableRecord ms, Transaction tr, Point3d p1, Point3d p2)
        {
            var ln = new Line(p1, p2) { Layer = CapaPendientes };
            ms.AppendEntity(ln); tr.AddNewlyCreatedDBObject(ln, true);
        }

        static void AsegurarCapas(Database db, Transaction tr)
        {
            AsegurarCapa(db, tr, CapaTuberias, 3);      // verde
            AsegurarCapa(db, tr, CapaBuzones, 4);       // cian
            AsegurarCapa(db, tr, CapaPendientes, 2);    // amarillo
        }

        static void AsegurarCapa(Database db, Transaction tr, string nombre, short aci)
        {
            LayerTable lt = tr.GetObject(db.LayerTableId, OpenMode.ForRead) as LayerTable;
            if (lt.Has(nombre)) return;
            lt.UpgradeOpen();
            var ltr = new LayerTableRecord
            {
                Name = nombre,
                Color = Autodesk.AutoCAD.Colors.Color.FromColorIndex(Autodesk.AutoCAD.Colors.ColorMethod.ByAci, aci)
            };
            lt.Add(ltr); tr.AddNewlyCreatedDBObject(ltr, true);
        }
    }
}
