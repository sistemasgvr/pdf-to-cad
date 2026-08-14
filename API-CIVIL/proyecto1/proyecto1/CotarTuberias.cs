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
//  COTAR_TUBERIAS — Coloca un MLeader (multileader) en cada nodo o quiebre
//  de las tuberías de gravedad, con la propiedad "Elevación de rasante" del
//  extremo correspondiente.
//
//  Regla:
//    · Si el punto es INICIO de al menos una tubería → StartInvertElevation
//      (Elevación de rasante inicial) de esa tubería.
//    · Si el punto es SOLO fin de tubería (última punta, no arranca ninguna
//      otra desde ahí) → EndInvertElevation (Elevación de rasante final).
//
//  MLeader:
//    · Punta de flecha en el punto de la tubería.
//    · Texto en la cola (arriba-derecha con offset proporcional).
//    · Attachment del texto al medio-izquierda → queda pegado al final de
//      la línea del leader.
//    · Capa dedicada "COTAS_TUBERIAS" (verde ACI 3).
// ============================================================================

namespace Civil3DBasico
{
    public class ComandosCotarTuberias
    {
        // Cada punto único de la red: coord, rasante a mostrar, y si es
        // "inicio de tubería" (marca esa cota como definitiva; ya no la
        // pisa un EndInvert que caiga en el mismo punto).
        private class NodoInfo
        {
            public Point3d Pt;
            public double  Rasante;
            public bool    EsInicio;
        }

        [CommandMethod("COTAR_TUBERIAS")]
        public void CotarTuberias()
        {
            Document doc = Application.DocumentManager.MdiActiveDocument;
            if (doc == null) return;
            Editor ed = doc.Editor;
            Database db = doc.Database;
            CivilDocument civilDoc = CivilApplication.ActiveDocument;

            ed.WriteMessage("\n═══ COTAR TUBERÍAS — MLeaders con Elevación de rasante ═══");

            var nodos = new Dictionary<string, NodoInfo>();
            int nRedes = 0, nTubos = 0;

            using (Transaction tr = db.TransactionManager.StartTransaction())
            {
                try
                {
                    // 1) Recolectar puntos + rasantes de TODAS las redes: gravedad,
                    //    conduit y presión. StartPoint.Z siempre es el EJE del tubo;
                    //    la rasante = eje − radio_interior.
                    //    Prioridad: si es inicio de una tubería, se marca EsInicio=true
                    //    y su rasante ya no se sobreescribe con un EndInvert que caiga
                    //    en el mismo punto (típico nodo interior de red).

                    // Redes de gravedad (y conduit — usan el mismo tipo Network)
                    ObjectIdCollection nets = civilDoc.GetPipeNetworkIds();
                    foreach (ObjectId nid in nets)
                    {
                        CivilDB.Network net = tr.GetObject(nid, OpenMode.ForRead) as CivilDB.Network;
                        if (net == null) continue;
                        nRedes++;
                        foreach (ObjectId pid in net.GetPipeIds())
                        {
                            CivilDB.Pipe p = tr.GetObject(pid, OpenMode.ForRead) as CivilDB.Pipe;
                            if (p == null) continue;
                            nTubos++;
                            double r = 0.0;
                            try { r = p.InnerDiameterOrWidth / 2.0; } catch { }
                            double sInv = p.StartPoint.Z - r;
                            double eInv = p.EndPoint.Z   - r;
                            AddOrUpdate(nodos, p.StartPoint, sInv, esInicio: true);
                            AddOrUpdate(nodos, p.EndPoint,   eInv, esInicio: false);
                        }
                    }

                    // Redes de presión (agua/gas). NominalDiameter en presión viene
                    // en PULGADAS → convertir a pies para restar del StartPoint.Z (ft).
                    ObjectIdCollection presNets = civilDoc.GetPressurePipeNetworkIds();
                    foreach (ObjectId nid in presNets)
                    {
                        CivilDB.PressurePipeNetwork net =
                            tr.GetObject(nid, OpenMode.ForRead) as CivilDB.PressurePipeNetwork;
                        if (net == null) continue;
                        nRedes++;
                        foreach (ObjectId pid in net.GetPipeIds())
                        {
                            CivilDB.PressurePipe p =
                                tr.GetObject(pid, OpenMode.ForRead) as CivilDB.PressurePipe;
                            if (p == null) continue;
                            nTubos++;
                            double r = 0.0;
                            try { r = (p.NominalDiameter / 12.0) / 2.0; } catch { }
                            double sInv = p.StartPoint.Z - r;
                            double eInv = p.EndPoint.Z   - r;
                            AddOrUpdate(nodos, p.StartPoint, sInv, esInicio: true);
                            AddOrUpdate(nodos, p.EndPoint,   eInv, esInicio: false);
                        }
                    }

                    if (nodos.Count == 0)
                    {
                        ed.WriteMessage("\n(No hay tuberías de gravedad en el dibujo — no se generaron leaders.)");
                        tr.Commit(); return;
                    }

                    // 2) Layer dedicado
                    const string capa = "COTAS_TUBERIAS";
                    LayerTable lt = tr.GetObject(db.LayerTableId, OpenMode.ForRead) as LayerTable;
                    if (!lt.Has(capa))
                    {
                        lt.UpgradeOpen();
                        var ltr = new LayerTableRecord {
                            Name = capa,
                            Color = Autodesk.AutoCAD.Colors.Color.FromColorIndex(
                                Autodesk.AutoCAD.Colors.ColorMethod.ByAci, 3)
                        };
                        lt.Add(ltr); tr.AddNewlyCreatedDBObject(ltr, true);
                    }

                    // 3) Tamaño del texto/flecha/offset — usamos como referencia
                    //    el diámetro medio de las tuberías. Así todo el leader queda
                    //    proporcional a los elementos del dibujo, sin importar escala.
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
                    // Pressure pipes: NominalDiameter viene en pulgadas → pies
                    foreach (ObjectId nid in presNets)
                    {
                        CivilDB.PressurePipeNetwork n2 =
                            tr.GetObject(nid, OpenMode.ForRead) as CivilDB.PressurePipeNetwork;
                        if (n2 == null) continue;
                        foreach (ObjectId pid in n2.GetPipeIds())
                        {
                            CivilDB.PressurePipe p2 =
                                tr.GetObject(pid, OpenMode.ForRead) as CivilDB.PressurePipe;
                            if (p2 == null) continue;
                            try { sumDia += p2.NominalDiameter / 12.0; nDia++; } catch { }
                        }
                    }
                    double diaMedio = nDia > 0 ? sumDia / nDia : 1.0;
                    if (diaMedio < 0.1) diaMedio = 1.0;
                    // Texto ≈ 1.2× diámetro medio (legible al lado de la tubería)
                    double txtH = diaMedio * 1.2;
                    // Cola/offset ≈ 3× diámetro (leader corto, no cruza por encima del buzón)
                    double off  = diaMedio * 3.0;

                    // 4) Crear MLeader por nodo
                    BlockTable bt = tr.GetObject(db.BlockTableId, OpenMode.ForRead) as BlockTable;
                    BlockTableRecord ms = tr.GetObject(bt[BlockTableRecord.ModelSpace],
                        OpenMode.ForWrite) as BlockTableRecord;

                    int nCreados = 0;
                    foreach (var kv in nodos)
                    {
                        var nd = kv.Value;
                        // Flecha en el punto de la tubería
                        Point3d flecha = new Point3d(nd.Pt.X, nd.Pt.Y, 0.0);
                        // Cola (donde queda pegado el texto) — desplazada arriba-derecha
                        Point3d cola   = new Point3d(nd.Pt.X + off, nd.Pt.Y + off, 0.0);

                        MLeader ml = new MLeader();
                        ml.SetDatabaseDefaults();
                        ml.Layer = capa;
                        ml.ContentType = ContentType.MTextContent;
                        // Tamaños proporcionales al diámetro de tubería — SIEMPRE explícitos
                        // (el estilo MLeader por defecto suele traer flecha desproporcionada).
                        try { ml.TextHeight   = txtH; } catch { }
                        try { ml.ArrowSize    = txtH * 0.6; } catch { }
                        try { ml.DoglegLength = txtH * 1.5; } catch { }
                        try { ml.LandingGap   = txtH * 0.4; } catch { }
                        try { ml.EnableLanding = true; } catch { }

                        MText mt = new MText();
                        mt.SetDatabaseDefaults();
                        mt.Contents = nd.Rasante.ToString("F2");
                        mt.TextHeight = txtH;
                        mt.Location = cola;
                        // Que el punto "Location" del MText coincida con el extremo
                        // izquierdo-medio del texto → el leader entra por la izquierda
                        // del número y el número queda a la derecha de la cola.
                        mt.Attachment = AttachmentPoint.MiddleLeft;
                        ml.MText = mt;

                        // Agregar la línea del leader: primer vértice = flecha
                        int idx = ml.AddLeaderLine(flecha);

                        ms.AppendEntity(ml);
                        tr.AddNewlyCreatedDBObject(ml, true);
                        nCreados++;
                    }

                    tr.Commit();
                    ed.WriteMessage($"\n✓ Redes procesadas: {nRedes}  ·  Tuberías: {nTubos}  ·  MLeaders creados: {nCreados}");
                    ed.WriteMessage($"\n  Layer: COTAS_TUBERIAS (verde).");
                    ed.WriteMessage($"\n  Texto = Elevación de rasante (inicial en cada nodo; final en la última punta).");
                }
                catch (Exception ex)
                {
                    ed.WriteMessage($"\n✗ Error: {ex.Message}");
                    tr.Abort();
                }
            }
        }

        static string Key(Point3d p)
        {
            return $"{Math.Round(p.X, 3):F3}|{Math.Round(p.Y, 3):F3}";
        }

        static void AddOrUpdate(Dictionary<string, NodoInfo> d, Point3d pt, double rasante, bool esInicio)
        {
            string k = Key(pt);
            if (!d.TryGetValue(k, out var existing))
            {
                d[k] = new NodoInfo { Pt = pt, Rasante = rasante, EsInicio = esInicio };
                return;
            }
            // Si el existente ya es inicio, no lo sobreescribimos con un end.
            if (existing.EsInicio) return;
            // Si el existente era end y ahora llega como inicio, promovemos.
            if (esInicio)
            {
                existing.Rasante = rasante;
                existing.EsInicio = true;
            }
            // Si ambos son end (raro), dejamos el primero — es un end terminal.
        }
    }
}
