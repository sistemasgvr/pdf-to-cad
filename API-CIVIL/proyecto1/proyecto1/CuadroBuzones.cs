using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.RegularExpressions;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.Colors;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.EditorInput;
using Autodesk.AutoCAD.Geometry;
using Autodesk.AutoCAD.Runtime;
using Autodesk.Civil.ApplicationServices;
using CivilDB = Autodesk.Civil.DatabaseServices;
using Exception = System.Exception;

// ============================================================================
//  CUADRO_BUZONES — dos tablas resumen, una debajo de la otra, a partir de UN
//  solo punto de inserción:
//   1) CUADRO DE BUZONES: ESTRUCTURA · C.T. · C.F. · ALTURA
//   2) CUADRO DE TUBERÍA: TUBERÍA · LONGITUD · C.I. · C.D. · PENDIENTE ·
//      DIÁMETRO · DESCARGA A
//      "C.I."/"C.D."/"Descarga a" se determinan por ELEVACIÓN, no por cuál
//      extremo Civil3D llama Start/End: el extremo con la cota MÁS BAJA es
//      siempre el de descarga (así se valida que el sentido sea consistente
//      con flujo por gravedad, sin asumir que Start=aguas arriba).
//   Ambas tablas miden el ancho REAL de cada texto (GeometricExtents) antes
//   de fijar el ancho de columnas — nunca se adivina un ancho por caracteres,
//   así no se superponen sin importar la fuente/estilo de texto activo.
// ============================================================================

namespace Civil3DBasico
{
    public class ComandosCuadroBuzones
    {
        private class FilaBuzon
        {
            public string Nombre;
            public double Tapa;    // C.T. = RimElevation
            public double Fondo;   // C.F. = SumpElevation
            public double Altura;  // Structure.Height ("Altura de estructura" real de Civil3D)
        }

        private class FilaTuberia
        {
            public string Nombre;
            public double Longitud;
            public double CotaInicio;      // extremo con MAYOR cota (aguas arriba)
            public double CotaDescarga;    // extremo con MENOR cota (aguas abajo)
            public string DescargaA;       // nombre de la estructura del extremo aguas abajo
            public string DiametroTexto;   // "15.0 in" (circular) o "15.0 x 12.0 in" (rectangular/otra forma)
            public double Pendiente => Longitud > 1e-6 ? (CotaInicio - CotaDescarga) / Longitud * 100.0 : 0.0;
        }

        private static class Estilo
        {
            public const string Capa = "CUADRO_BUZONES";
            public const short Titulo = 7;       // blanco
            public const short Encabezado = 4;   // cian
            public const short Dato = 9;          // gris claro
            public const short Marco = 7;          // blanco

            public const double TxtTitulo = 0.9, TxtEncabezado = 0.55, TxtDato = 0.5;
            public const double Interlineado = 1.8;
            public const double Padding = 1.4;     // relleno horizontal a cada lado del texto más ancho
            public const double GapEntreTablas = 3.0;   // separación entre el cuadro de buzones y el de tubería
        }

        [CommandMethod("CUADRO_BUZONES")]
        public void CuadroBuzones()
        {
            Document doc = Application.DocumentManager.MdiActiveDocument;
            if (doc == null) return;
            Editor ed = doc.Editor;
            Database db = doc.Database;
            CivilDocument civilDoc = CivilApplication.ActiveDocument;

            using (Transaction tr = db.TransactionManager.StartTransaction())
            {
                try
                {
                    var buzones = new List<FilaBuzon>();
                    var tuberias = new List<FilaTuberia>();

                    ObjectIdCollection nets = civilDoc.GetPipeNetworkIds();
                    foreach (ObjectId nid in nets)
                    {
                        CivilDB.Network net = tr.GetObject(nid, OpenMode.ForRead) as CivilDB.Network;
                        if (net == null) continue;

                        foreach (ObjectId sid in net.GetStructureIds())
                        {
                            try
                            {
                                CivilDB.Structure st = tr.GetObject(sid, OpenMode.ForRead) as CivilDB.Structure;
                                if (st == null) continue;
                                string nombre; try { nombre = st.Name; } catch { nombre = "?"; }
                                double tapa; try { tapa = st.RimElevation; } catch { continue; }
                                double fondo; try { fondo = st.SumpElevation; } catch { continue; }
                                // "Altura de estructura" real de Civil3D (Structure.Height), no
                                // CT−CF a mano — si no se puede leer, se cae al cálculo simple.
                                double altura; try { altura = st.Height; } catch { altura = tapa - fondo; }
                                buzones.Add(new FilaBuzon { Nombre = nombre, Tapa = tapa, Fondo = fondo, Altura = altura });
                            }
                            catch { }
                        }

                        foreach (ObjectId pid in net.GetPipeIds())
                        {
                            try
                            {
                                CivilDB.Pipe p = tr.GetObject(pid, OpenMode.ForRead) as CivilDB.Pipe;
                                if (p == null) continue;

                                double invA = ComandosCotarTuberias.InvertEnNodo(p.StartStructureId, p.StartPoint, p, tr);
                                double invB = ComandosCotarTuberias.InvertEnNodo(p.EndStructureId, p.EndPoint, p, tr);
                                bool startEsAguasArriba = invA >= invB;

                                ObjectId structDescargaId = startEsAguasArriba ? p.EndStructureId : p.StartStructureId;
                                string nombreDescarga = "—";
                                if (!structDescargaId.IsNull && structDescargaId.IsValid)
                                {
                                    try
                                    {
                                        var stD = tr.GetObject(structDescargaId, OpenMode.ForRead) as CivilDB.Structure;
                                        if (stD != null) nombreDescarga = stD.Name;
                                    }
                                    catch { }
                                }

                                double longitud = 0.0;
                                try { longitud = p.Length2DCenterToCenter; } catch { try { longitud = p.Length2D; } catch { } }

                                string nombrePipe; try { nombrePipe = p.Name; } catch { nombrePipe = "?"; }

                                tuberias.Add(new FilaTuberia
                                {
                                    Nombre = nombrePipe,
                                    Longitud = longitud,
                                    CotaInicio = startEsAguasArriba ? invA : invB,
                                    CotaDescarga = startEsAguasArriba ? invB : invA,
                                    DescargaA = nombreDescarga,
                                    DiametroTexto = FormatoDiametro(p),
                                });
                            }
                            catch { }
                        }
                    }

                    if (buzones.Count == 0 && tuberias.Count == 0)
                    {
                        ed.WriteMessage("\n(No hay buzones ni tuberías de gravedad en el dibujo.)");
                        tr.Commit(); return;
                    }

                    buzones = buzones.OrderBy(f => f.Nombre, new ComparadorNatural()).ToList();
                    tuberias = tuberias.OrderBy(f => f.Nombre, new ComparadorNatural()).ToList();

                    PromptPointResult pIns = ed.GetPoint("\nPunto de inserción de los cuadros:");
                    if (pIns.Status != PromptStatus.OK) { tr.Abort(); return; }
                    Point3d insWcs = pIns.Value.TransformBy(ed.CurrentUserCoordinateSystem);

                    AsegurarCapa(db, tr);
                    BlockTable bt = tr.GetObject(db.BlockTableId, OpenMode.ForRead) as BlockTable;
                    BlockTableRecord ms = tr.GetObject(bt[BlockTableRecord.ModelSpace], OpenMode.ForWrite) as BlockTableRecord;

                    Point3d cursor = insWcs;
                    if (buzones.Count > 0)
                    {
                        var columnas = new List<(string encabezado, List<string> valores)>
                        {
                            ("ESTRUCTURA", buzones.Select(f => "BUZÓN " + f.Nombre).ToList()),
                            ("C.T.", buzones.Select(f => f.Tapa.ToString("F2")).ToList()),
                            ("C.F.", buzones.Select(f => f.Fondo.ToString("F2")).ToList()),
                            ("ALTURA", buzones.Select(f => $"{f.Altura:F2} ft").ToList()),
                        };
                        double alto = DibujarTablaSimple(ms, tr, cursor, "CUADRO DE BUZONES", columnas,
                            "C.T. = COTA TAPA      C.F. = COTA FONDO");
                        cursor = new Point3d(cursor.X, cursor.Y - alto - Estilo.GapEntreTablas, 0);
                    }

                    if (tuberias.Count > 0)
                    {
                        var columnas = new List<(string encabezado, List<string> valores)>
                        {
                            ("TUBERÍA", tuberias.Select(f => f.Nombre).ToList()),
                            ("LONGITUD", tuberias.Select(f => $"{f.Longitud:F2} ft").ToList()),
                            ("C.I.", tuberias.Select(f => f.CotaInicio.ToString("F2")).ToList()),
                            ("C.D.", tuberias.Select(f => f.CotaDescarga.ToString("F2")).ToList()),
                            ("PENDIENTE", tuberias.Select(f => $"{f.Pendiente:F2} %").ToList()),
                            ("DIÁMETRO", tuberias.Select(f => f.DiametroTexto).ToList()),
                            ("DESCARGA A", tuberias.Select(f => f.DescargaA).ToList()),
                        };
                        DibujarTablaSimple(ms, tr, cursor, "CUADRO DE TUBERÍA", columnas,
                            "C.I. = COTA DE INICIO      C.D. = COTA DE DESCARGA");
                    }

                    tr.Commit();
                    ed.WriteMessage($"\n✓ Generado: {buzones.Count} buzones, {tuberias.Count} tuberías.");
                }
                catch (Exception ex)
                {
                    ed.WriteMessage($"\nError: {ex.Message}");
                    tr.Abort();
                }
            }
        }

        // Dibuja una tabla genérica: título + encabezado + N filas de datos + fila final
        // unificada con la leyenda. El ancho de cada columna se calcula midiendo el
        // ANCHO REAL (GeometricExtents) del encabezado y de todos sus valores — nunca
        // se estima por conteo de caracteres, así el texto nunca se monta sobre la
        // columna vecina sin importar la fuente/estilo activo. Devuelve la altura total
        // dibujada, para poder apilar la siguiente tabla justo debajo.
        private static double DibujarTablaSimple(BlockTableRecord ms, Transaction tr, Point3d origen,
            string titulo, List<(string encabezado, List<string> valores)> columnas, string leyenda)
        {
            int nFilas = columnas[0].valores.Count;

            var anchos = new List<double>();
            foreach (var col in columnas)
            {
                double ancho = MedirAncho(ms, tr, col.encabezado, Estilo.TxtEncabezado);
                foreach (var v in col.valores)
                    ancho = Math.Max(ancho, MedirAncho(ms, tr, v, Estilo.TxtDato));
                anchos.Add(ancho + Estilo.TxtDato * Estilo.Padding);
            }
            double anchoTotal = anchos.Sum();

            double alturaFila = Estilo.TxtDato * Estilo.Interlineado * 1.6;
            double alturaTitulo = Estilo.TxtTitulo * Estilo.Interlineado * 1.3;
            double alturaTotal = alturaTitulo + alturaFila * (2 + nFilas);   // título + encabezado + datos + leyenda

            DrawRectPoly(ms, tr, origen, new Point3d(origen.X + anchoTotal, origen.Y - alturaTotal, 0), Estilo.Marco, Estilo.TxtDato * 0.06);

            double y = origen.Y;
            DrawLine(ms, tr, new Point3d(origen.X, y - alturaTitulo, 0), new Point3d(origen.X + anchoTotal, y - alturaTitulo, 0), Estilo.Marco);
            DrawText(ms, tr, titulo, new Point3d(origen.X + anchoTotal / 2.0, y - alturaTitulo / 2.0, 0),
                Estilo.TxtTitulo, Estilo.Titulo, AttachmentPoint.MiddleCenter);
            y -= alturaTitulo;

            var xCentros = new List<double>();
            var xBordes = new List<double> { origen.X };
            double acumulado = origen.X;
            foreach (var a in anchos) { xCentros.Add(acumulado + a / 2.0); acumulado += a; xBordes.Add(acumulado); }

            double yDivTop = y, yDivBottom = y - alturaFila * (1 + nFilas);
            for (int i = 1; i < xBordes.Count - 1; i++)
                DrawLine(ms, tr, new Point3d(xBordes[i], yDivTop, 0), new Point3d(xBordes[i], yDivBottom, 0), Estilo.Marco);

            for (int c = 0; c < columnas.Count; c++)
                DrawText(ms, tr, columnas[c].encabezado, new Point3d(xCentros[c], y - alturaFila / 2.0, 0),
                    Estilo.TxtEncabezado, Estilo.Encabezado, AttachmentPoint.MiddleCenter);
            y -= alturaFila;
            DrawLine(ms, tr, new Point3d(origen.X, y, 0), new Point3d(origen.X + anchoTotal, y, 0), Estilo.Marco);

            for (int f = 0; f < nFilas; f++)
            {
                double yc = y - alturaFila / 2.0;
                for (int c = 0; c < columnas.Count; c++)
                    DrawText(ms, tr, columnas[c].valores[f], new Point3d(xCentros[c], yc, 0),
                        Estilo.TxtDato, Estilo.Dato, AttachmentPoint.MiddleCenter);
                y -= alturaFila;
                DrawLine(ms, tr, new Point3d(origen.X, y, 0), new Point3d(origen.X + anchoTotal, y, 0), Estilo.Marco);
            }

            double yLeyenda = y - alturaFila / 2.0;
            DrawText(ms, tr, leyenda, new Point3d(origen.X + anchoTotal / 2.0, yLeyenda, 0),
                Estilo.TxtDato, Estilo.Encabezado, AttachmentPoint.MiddleCenter);

            return alturaTotal;
        }

        // Diámetro COMPLETO de la tubería: "15.0 in" si es circular, "15.0 x 12.0 in" si
        // es rectangular/otra forma (InnerDiameterOrWidth = ancho, InnerHeight = alto) —
        // antes solo se mostraba el ancho, que en una tubería rectangular no representa
        // la sección completa.
        private static string FormatoDiametro(CivilDB.Pipe p)
        {
            double ancho = 0.0; try { ancho = p.InnerDiameterOrWidth * 12.0; } catch { }
            try
            {
                if (p.CrossSectionalShape != CivilDB.SweptShapeType.Circular)
                {
                    double alto = 0.0; try { alto = p.InnerHeight * 12.0; } catch { }
                    if (alto > 0.05 && Math.Abs(alto - ancho) > 0.05)
                        return $"{ancho:F1} x {alto:F1} in";
                }
            }
            catch { }
            return $"{ancho:F1} in";
        }

        // Crea un MText temporal solo para medir su ancho REAL (GeometricExtents) y lo
        // borra de inmediato. Así el ancho de columna nunca se adivina.
        private static double MedirAncho(BlockTableRecord ms, Transaction tr, string texto, double altura)
        {
            if (string.IsNullOrEmpty(texto)) return 0.0;
            var mt = new MText();
            mt.SetDatabaseDefaults();
            mt.Contents = texto;
            mt.TextHeight = altura;
            mt.Location = Point3d.Origin;
            ms.AppendEntity(mt);
            tr.AddNewlyCreatedDBObject(mt, true);
            double ancho;
            try
            {
                Extents3d ext = mt.GeometricExtents;
                ancho = ext.MaxPoint.X - ext.MinPoint.X;
            }
            catch { ancho = texto.Length * altura * 0.85; }   // respaldo si no se pudo medir
            try { mt.Erase(); } catch { }
            return ancho;
        }

        // Ordena "BZ-1, BZ-2, ..., BZ-10" / "Pipe1, Pipe2, ..." numéricamente, no
        // alfabéticamente (que dejaría el 10 antes que el 2).
        private class ComparadorNatural : IComparer<string>
        {
            public int Compare(string a, string b)
            {
                var (pa, na) = Partes(a);
                var (pb, nb) = Partes(b);
                int c = string.Compare(pa, pb, StringComparison.OrdinalIgnoreCase);
                if (c != 0) return c;
                if (na.HasValue && nb.HasValue) return na.Value.CompareTo(nb.Value);
                return string.Compare(a, b, StringComparison.OrdinalIgnoreCase);
            }
            private static (string prefijo, int? numero) Partes(string s)
            {
                if (string.IsNullOrEmpty(s)) return ("", null);
                var m = Regex.Match(s, @"^(.*?)(\d+)\s*$");
                if (m.Success && int.TryParse(m.Groups[2].Value, out int n))
                    return (m.Groups[1].Value, n);
                return (s, null);
            }
        }

        // ── Helpers de bajo nivel (independientes del resto del proyecto) ──

        private static void DrawLine(BlockTableRecord ms, Transaction tr, Point3d p1, Point3d p2, short color)
        {
            var ln = new Line(p1, p2) { Layer = Estilo.Capa, Color = Color.FromColorIndex(ColorMethod.ByAci, color) };
            ms.AppendEntity(ln); tr.AddNewlyCreatedDBObject(ln, true);
        }

        private static void DrawRectPoly(BlockTableRecord ms, Transaction tr, Point3d esqA, Point3d esqB, short color, double width = 0)
        {
            var pl = new Polyline();
            pl.AddVertexAt(0, new Point2d(esqA.X, esqA.Y), 0, 0, 0);
            pl.AddVertexAt(1, new Point2d(esqB.X, esqA.Y), 0, 0, 0);
            pl.AddVertexAt(2, new Point2d(esqB.X, esqB.Y), 0, 0, 0);
            pl.AddVertexAt(3, new Point2d(esqA.X, esqB.Y), 0, 0, 0);
            pl.Closed = true;
            pl.Layer = Estilo.Capa;
            pl.Color = Color.FromColorIndex(ColorMethod.ByAci, color);
            if (width > 0) pl.ConstantWidth = width;
            ms.AppendEntity(pl); tr.AddNewlyCreatedDBObject(pl, true);
        }

        private static void DrawText(BlockTableRecord ms, Transaction tr, string contenido, Point3d loc,
            double altura, short color, AttachmentPoint attach)
        {
            var mt = new MText();
            mt.SetDatabaseDefaults();
            mt.Layer = Estilo.Capa;
            mt.Color = Color.FromColorIndex(ColorMethod.ByAci, color);
            mt.Contents = contenido;
            mt.TextHeight = altura;
            mt.Location = loc;
            mt.Attachment = attach;
            ms.AppendEntity(mt); tr.AddNewlyCreatedDBObject(mt, true);
        }

        private static void AsegurarCapa(Database db, Transaction tr)
        {
            LayerTable lt = tr.GetObject(db.LayerTableId, OpenMode.ForRead) as LayerTable;
            if (lt.Has(Estilo.Capa)) return;
            lt.UpgradeOpen();
            var ltr = new LayerTableRecord { Name = Estilo.Capa, Color = Color.FromColorIndex(ColorMethod.ByAci, 7) };
            lt.Add(ltr); tr.AddNewlyCreatedDBObject(ltr, true);
        }
    }
}
