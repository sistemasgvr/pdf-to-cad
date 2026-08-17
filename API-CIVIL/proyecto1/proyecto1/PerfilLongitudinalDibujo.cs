using System;
using System.Collections.Generic;
using System.Linq;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using Autodesk.AutoCAD.Colors;
using CivilDB = Autodesk.Civil.DatabaseServices;
using static Civil3DBasico.PerfilLongitudinalDatos;

// ============================================================================
//  PERFIL LONGITUDINAL — hoja de dibujo profesional generada 100% con
//  entidades propias (Line/Polyline/MText). NO usa ProfileView nativo: así el
//  punto de inserción es siempre exactamente donde el usuario hace clic, y el
//  layout (encabezado, grilla, tabla, leyenda) queda bajo control total.
//
//  Sistema de coordenadas (clase Sistema, más abajo): Origen = punto clicado
//  = esquina superior-izquierda de toda la hoja. Todo lo demás (grilla, ejes,
//  tabla, leyenda) se ubica relativo a Origen con Sistema.X(estación) /
//  Sistema.Y(cota). Todo tamaño/espaciado sale de UnidadBase, calculada según
//  el largo real de la red → la hoja escala sola con cualquier recorrido.
// ============================================================================

namespace Civil3DBasico
{
    internal static class PerfilLongitudinalDibujo
    {
        // ── Estilo: colores (ACI) y proporciones. Nada de números mágicos sueltos
        //    en los métodos de dibujo — todo constante o derivado de UnidadBase. ──
        private static class Estilo
        {
            public const string Capa = "PERFIL_LONGITUDINAL";
            public const string LinetypeGrid = "DASHED";

            public const short Titulo = 7;            // blanco
            public const short Subtitulo = 4;          // cian
            public const short Terreno = 3;             // verde
            public const short Tuberia = 5;              // azul
            public const short Cota = 2;                  // amarillo
            public const short Secundario = 9;             // gris claro
            public const short ValorImportante = 4;         // cian
            public const short Marco = 7;                    // blanco
            public const short Grid = 8;                      // gris (rejilla suave)
            public const short Buzon = 7;                       // blanco

            public const double PropTitulo = 3.0;
            public const double PropSubtitulo = 2.0;
            public const double PropNormal = 1.3;
            public const double PropPequeno = 1.0;
            public const double PropAlturaHeader = 16.0;
            public const double PropAlturaFila = 3.4;
            public const double PropAnchoEjeY = 15.0;      // ancho para "COTA TERRENO (ft)" sin chocar con la 1ª columna
            public const double PropAnchoLeyenda = 22.0;
            public const double PropAnchoBuzon = 5.0;
            public const double FraccionAltoGrid = 0.30;   // alto de grilla ≈ 30% de su ancho
            public const double PropAlturaEtiquetaSup = 8.5;  // franja arriba de la grilla para nombre+progresiva del buzón
            public const double PropGapGridTabla = 2.2;       // separación entre la última cota (eje) y la tabla

            // MText real ocupa ~1.66× su TextHeight nominal de alto de línea — los
            // multiplicadores de espaciado entre líneas apiladas usan este factor
            // (u otro mayor) para que nunca se toquen visualmente.
            public const double Interlineado = 1.75;
        }

        // ── Sistema de coordenadas base: TODO el dibujo depende de esta clase. ──
        private class Sistema
        {
            public Point3d Origen;          // = punto clicado = esquina sup-izq de la hoja
            public double EstacionBase;
            public double CotaMin, CotaMax, PasoCota;
            public double ExagVertical;
            public double UnidadBase;
            public double AnchoEjeY;
            public double AnchoDatos;
            public double AlturaHeader, AlturaFila, AlturaGrid, AlturaEtiquetaSup, AlturaGapGridTabla;
            public double YHeaderBottom, YGridTop, YPlotTop, YGridBottom, YTableTop, YTableBottom;
            public bool MostrarTerreno, MostrarTapa;
            public bool DiametroConstante;
            public string DiametroConstanteTexto;
            public string MaterialConstante;
            public int NumFilasTabla;

            public const double EscalaH = 1.0;   // horizontal a escala real: 1 pie dibujo = 1 pie de estación
            public double AnchoGrid => AnchoEjeY + AnchoDatos;
            public double XDer => Origen.X + AnchoGrid;

            public double X(double station) => Origen.X + AnchoEjeY + (station - EstacionBase) * EscalaH;
            public double Y(double elevation) => YGridBottom + (elevation - CotaMin) * ExagVertical;
        }

        // ════════════════════════════════════════════════════════════════════
        //  PUNTO DE ENTRADA
        // ════════════════════════════════════════════════════════════════════
        public static void Generar(Point3d origenClic, CivilDB.Network net,
            List<NodoBuzon> nodos, List<TramoPipe> tramos, List<PuntoTerreno> terreno,
            Database db, Transaction tr)
        {
            if (nodos == null || nodos.Count < 2) return;

            AsegurarCapa(db, tr);
            BlockTable bt = tr.GetObject(db.BlockTableId, OpenMode.ForRead) as BlockTable;
            BlockTableRecord ms = tr.GetObject(bt[BlockTableRecord.ModelSpace], OpenMode.ForWrite) as BlockTableRecord;

            Sistema s = ConstruirSistema(origenClic, nodos, tramos, terreno);

            DrawFrame(ms, tr, s);
            DrawGrid(ms, tr, s, nodos);
            DrawAxes(ms, tr, s);
            DrawTerreno(ms, tr, s, terreno);
            DrawPipe(ms, tr, s, tramos);
            DrawStructures(ms, tr, s, nodos, terreno);
            DrawSlopeLabels(ms, tr, s, tramos);
            DrawHeader(ms, tr, s, net, nodos);
            DrawBottomTable(ms, tr, s, nodos, tramos, terreno);
            DrawLegend(ms, tr, s);
        }

        // ════════════════════════════════════════════════════════════════════
        //  SISTEMA DE COORDENADAS — todo el layout (tamaños, rango de cotas,
        //  exageración vertical, filas de tabla que existen) se decide UNA vez
        //  aquí, a partir únicamente de los datos reales de la red.
        // ════════════════════════════════════════════════════════════════════
        private static Sistema ConstruirSistema(Point3d origen,
            List<NodoBuzon> nodos, List<TramoPipe> tramos, List<PuntoTerreno> terreno)
        {
            double staMin = nodos[0].Station, staMax = nodos[nodos.Count - 1].Station;
            double rangoEstacion = Math.Max(staMax - staMin, 1.0);

            // Rango de cotas real: inverts + tapas (si existen) + terreno (si existe).
            double elevMin = double.MaxValue, elevMax = double.MinValue;
            foreach (var n in nodos)
            {
                if (n.Invert < elevMin) elevMin = n.Invert;
                if (n.Invert > elevMax) elevMax = n.Invert;
                double? rim = TryRim(n.St);
                if (rim.HasValue)
                {
                    if (rim.Value > elevMax) elevMax = rim.Value;
                    if (rim.Value < elevMin) elevMin = rim.Value;
                }
            }
            if (terreno != null)
                foreach (var t in terreno)
                {
                    if (t.Elevation < elevMin) elevMin = t.Elevation;
                    if (t.Elevation > elevMax) elevMax = t.Elevation;
                }
            if (elevMax <= elevMin) elevMax = elevMin + 1.0;

            double margen = Math.Max((elevMax - elevMin) * 0.15, 0.5);
            double paso = PasoLindo((elevMax - elevMin) + 2 * margen, 7);
            double cotaMin = Math.Floor((elevMin - margen) / paso) * paso;
            double cotaMax = Math.Ceiling((elevMax + margen) / paso) * paso;
            if (cotaMax <= cotaMin) cotaMax = cotaMin + paso;

            double unidad = Clamp(rangoEstacion * 0.01, 0.3, 3.0);

            bool mostrarTerreno = terreno != null && terreno.Count > 0;
            bool mostrarTapa = nodos.Any(n => TryRim(n.St).HasValue);

            bool diamConst = true; string diamTexto = ""; string material = "";
            if (tramos != null && tramos.Count > 0)
            {
                try { diamTexto = FormatoDiametro(tramos[0].P); } catch { }
                try { material = tramos[0].P.Description ?? ""; } catch { }
                foreach (var t in tramos)
                {
                    string d = ""; try { d = FormatoDiametro(t.P); } catch { }
                    if (d != diamTexto) { diamConst = false; break; }
                }
            }

            int numFilas = 1 + (mostrarTerreno ? 1 : 0) + (mostrarTapa ? 1 : 0) + 1 + 1 + 1 + 1;
            // Progresiva + [Terreno] + [Tapa] + Invert + Diámetro + Longitud + Pendiente

            var s = new Sistema
            {
                Origen = origen,
                EstacionBase = staMin,
                CotaMin = cotaMin,
                CotaMax = cotaMax,
                PasoCota = paso,
                UnidadBase = unidad,
                AnchoEjeY = unidad * Estilo.PropAnchoEjeY,
                AnchoDatos = rangoEstacion * Sistema.EscalaH + unidad * 6.0,
                AlturaHeader = unidad * Estilo.PropAlturaHeader,
                AlturaFila = unidad * Estilo.PropAlturaFila,
                AlturaEtiquetaSup = unidad * Estilo.PropAlturaEtiquetaSup,
                AlturaGapGridTabla = unidad * Estilo.PropGapGridTabla,
                MostrarTerreno = mostrarTerreno,
                MostrarTapa = mostrarTapa,
                DiametroConstante = diamConst,
                DiametroConstanteTexto = diamTexto,
                MaterialConstante = material,
                NumFilasTabla = numFilas,
            };

            double alturaGridObjetivo = s.AnchoGrid * Estilo.FraccionAltoGrid;
            s.ExagVertical = RedondearExageracion(alturaGridObjetivo / (cotaMax - cotaMin));
            s.AlturaGrid = (cotaMax - cotaMin) * s.ExagVertical;

            // Cadena vertical, de arriba hacia abajo:
            //   header → [franja nombre+progresiva de buzón] → grilla (CotaMax→CotaMin)
            //   → [separación] → tabla. Cada zona tiene su propio espacio reservado,
            //   así ningún texto de una zona puede pisar el de la zona vecina.
            s.YHeaderBottom = origen.Y - s.AlturaHeader;
            s.YGridTop = s.YHeaderBottom;
            s.YPlotTop = s.YGridTop - s.AlturaEtiquetaSup;
            s.YGridBottom = s.YPlotTop - s.AlturaGrid;
            s.YTableTop = s.YGridBottom - s.AlturaGapGridTabla;
            s.YTableBottom = s.YTableTop - s.NumFilasTabla * s.AlturaFila;

            return s;
        }

        // ════════════════════════════════════════════════════════════════════
        //  MÉTODOS DE DIBUJO — cada uno con una única responsabilidad.
        // ════════════════════════════════════════════════════════════════════

        private static void DrawFrame(BlockTableRecord ms, Transaction tr, Sistema s)
        {
            DrawRectPoly(ms, tr, new Point3d(s.Origen.X, s.Origen.Y, 0), new Point3d(s.XDer, s.YTableBottom, 0),
                Estilo.Marco, s.UnidadBase * 0.05);
            DrawLine(ms, tr, new Point3d(s.Origen.X, s.YHeaderBottom, 0), new Point3d(s.XDer, s.YHeaderBottom, 0), Estilo.Marco);
            DrawLine(ms, tr, new Point3d(s.Origen.X, s.YTableTop, 0), new Point3d(s.XDer, s.YTableTop, 0), Estilo.Marco);
        }

        private static void DrawGrid(BlockTableRecord ms, Transaction tr, Sistema s, List<NodoBuzon> nodos)
        {
            double xIzq = s.Origen.X + s.AnchoEjeY;
            for (double cota = s.CotaMin; cota <= s.CotaMax + 1e-6; cota += s.PasoCota)
            {
                double y = s.Y(cota);
                DrawLine(ms, tr, new Point3d(xIzq, y, 0), new Point3d(s.XDer, y, 0), Estilo.Grid, Estilo.LinetypeGrid);
            }
            foreach (var n in nodos)
            {
                double x = s.X(n.Station);
                DrawLine(ms, tr, new Point3d(x, s.YGridTop, 0), new Point3d(x, s.YGridBottom, 0), Estilo.Grid, Estilo.LinetypeGrid);
            }
        }

        private static void DrawAxes(BlockTableRecord ms, Transaction tr, Sistema s)
        {
            double xIzq = s.Origen.X + s.AnchoEjeY;
            DrawLine(ms, tr, new Point3d(xIzq, s.YGridBottom, 0), new Point3d(xIzq, s.YGridTop, 0), Estilo.Marco);
            DrawLine(ms, tr, new Point3d(s.XDer, s.YGridBottom, 0), new Point3d(s.XDer, s.YGridTop, 0), Estilo.Marco);

            double txt = s.UnidadBase * Estilo.PropPequeno;
            double tick = s.UnidadBase * 0.8;
            for (double cota = s.CotaMin; cota <= s.CotaMax + 1e-6; cota += s.PasoCota)
            {
                double y = s.Y(cota);
                DrawLine(ms, tr, new Point3d(xIzq - tick, y, 0), new Point3d(xIzq, y, 0), Estilo.Marco);
                DrawText(ms, tr, cota.ToString("F2"), new Point3d(xIzq - tick * 1.3, y, 0), txt, Estilo.Cota, AttachmentPoint.MiddleRight);
                DrawLine(ms, tr, new Point3d(s.XDer, y, 0), new Point3d(s.XDer + tick, y, 0), Estilo.Marco);
                DrawText(ms, tr, cota.ToString("F2"), new Point3d(s.XDer + tick * 1.3, y, 0), txt, Estilo.Cota, AttachmentPoint.MiddleLeft);
            }
        }

        private static void DrawTerreno(BlockTableRecord ms, Transaction tr, Sistema s, List<PuntoTerreno> terreno)
        {
            if (terreno == null || terreno.Count < 2) return;
            var pl = new Polyline();
            for (int i = 0; i < terreno.Count; i++)
                pl.AddVertexAt(i, new Point2d(s.X(terreno[i].Station), s.Y(terreno[i].Elevation)), 0, 0, 0);
            pl.Layer = Estilo.Capa;
            pl.Color = Color.FromColorIndex(ColorMethod.ByAci, Estilo.Terreno);
            ms.AppendEntity(pl); tr.AddNewlyCreatedDBObject(pl, true);
        }

        private static void DrawPipe(BlockTableRecord ms, Transaction tr, Sistema s, List<TramoPipe> tramos)
        {
            if (tramos == null || tramos.Count == 0) return;
            var pl = new Polyline();
            int i = 0;
            Point2d? anterior = null;
            foreach (var t in tramos)
            {
                var p1 = new Point2d(s.X(t.StaIni), s.Y(t.InvIni));
                var p2 = new Point2d(s.X(t.StaFin), s.Y(t.InvFin));
                if (anterior == null || anterior.Value.GetDistanceTo(p1) > 1e-6)
                    pl.AddVertexAt(i++, p1, 0, 0, 0);
                pl.AddVertexAt(i++, p2, 0, 0, 0);
                anterior = p2;
            }
            pl.Layer = Estilo.Capa;
            pl.Color = Color.FromColorIndex(ColorMethod.ByAci, Estilo.Tuberia);
            pl.ConstantWidth = s.UnidadBase * 0.5;
            ms.AppendEntity(pl); tr.AddNewlyCreatedDBObject(pl, true);
        }

        private static void DrawStructures(BlockTableRecord ms, Transaction tr, Sistema s,
            List<NodoBuzon> nodos, List<PuntoTerreno> terreno)
        {
            double anchoBz = s.UnidadBase * Estilo.PropAnchoBuzon;
            double txt = s.UnidadBase * Estilo.PropPequeno;
            double txtNombre = s.UnidadBase * Estilo.PropNormal;

            foreach (var n in nodos)
            {
                double x = s.X(n.Station);
                double? rim = TryRim(n.St);
                double yInv = s.Y(n.Invert);
                double yTop = rim.HasValue ? s.Y(rim.Value) : yInv + s.UnidadBase * 3.0;
                if (yTop < yInv) yTop = yInv + s.UnidadBase * 0.5;
                if (yTop > s.YPlotTop) yTop = s.YPlotTop;   // nunca invade la franja de nombre/progresiva

                DrawRectPoly(ms, tr, new Point3d(x - anchoBz / 2.0, yTop, 0), new Point3d(x + anchoBz / 2.0, yInv, 0), Estilo.Buzon);

                // Nombre + progresiva SIEMPRE dentro de la franja reservada arriba de la
                // grilla (YPlotTop..YGridTop) — nunca comparten altura con la etiqueta de
                // cota máxima del eje, que vive justo en YPlotTop.
                string nombre; try { nombre = n.St.Name; } catch { nombre = "?"; }
                double yNombre = s.YGridTop - s.UnidadBase * 1.2;
                DrawText(ms, tr, nombre, new Point3d(x, yNombre, 0), txtNombre, Estilo.Subtitulo, AttachmentPoint.BottomCenter);
                DrawText(ms, tr, "Prog. " + FormatEstacion(n.Station),
                    new Point3d(x, yNombre - txtNombre * Estilo.Interlineado, 0), txt, Estilo.Secundario, AttachmentPoint.BottomCenter);

                if (terreno != null && terreno.Count > 0)
                {
                    double? cotaTerr = InterpolarTerreno(terreno, n.Station);
                    if (cotaTerr.HasValue)
                        DrawText(ms, tr, cotaTerr.Value.ToString("F2"),
                            new Point3d(x, yTop + s.UnidadBase * 0.6, 0), txt, Estilo.Cota, AttachmentPoint.BottomCenter);
                }

                double yEtiquetaInf = yInv - s.UnidadBase * 1.1;
                if (rim.HasValue)
                {
                    DrawText(ms, tr, $"C.T. {rim.Value:F2}", new Point3d(x, yEtiquetaInf, 0), txt, Estilo.ValorImportante, AttachmentPoint.TopCenter);
                    yEtiquetaInf -= txt * Estilo.Interlineado;
                }
                DrawText(ms, tr, $"C.I. {n.Invert:F2}", new Point3d(x, yEtiquetaInf, 0), txt, Estilo.ValorImportante, AttachmentPoint.TopCenter);
            }
        }

        private static void DrawSlopeLabels(BlockTableRecord ms, Transaction tr, Sistema s, List<TramoPipe> tramos)
        {
            if (tramos == null) return;
            double txt = s.UnidadBase * Estilo.PropPequeno;
            foreach (var t in tramos)
            {
                double longitud = t.StaFin - t.StaIni;
                if (longitud < 1e-6) continue;
                double pendiente = (t.InvIni - t.InvFin) / longitud * 100.0;   // positivo = descendente
                double staMed = (t.StaIni + t.StaFin) / 2.0;
                double invMed = (t.InvIni + t.InvFin) / 2.0;
                double x = s.X(staMed);
                double y = s.Y(invMed) + s.UnidadBase * 2.2;   // arriba de la tubería, sin tocarla
                string texto = $"L = {longitud:F2} ft\\PS = {pendiente:F2} %";
                DrawText(ms, tr, texto, new Point3d(x, y, 0), txt, Estilo.Secundario, AttachmentPoint.BottomCenter);
            }
        }

        private static void DrawHeader(BlockTableRecord ms, Transaction tr, Sistema s, CivilDB.Network net, List<NodoBuzon> nodos)
        {
            double xCentro = (s.Origen.X + s.XDer) / 2.0;
            double txtTitulo = s.UnidadBase * Estilo.PropTitulo;
            double txtSub = s.UnidadBase * Estilo.PropSubtitulo;
            double txtPeq = s.UnidadBase * Estilo.PropPequeno;

            double yTitulo = s.Origen.Y - s.UnidadBase * 3.0;
            DrawText(ms, tr, "PERFIL LONGITUDINAL", new Point3d(xCentro, yTitulo, 0), txtTitulo, Estilo.Titulo, AttachmentPoint.MiddleCenter);

            double ySub = yTitulo - txtTitulo * Estilo.Interlineado;
            string nombreRed; try { nombreRed = net.Name; } catch { nombreRed = "?"; }
            DrawText(ms, tr, $"RED: {nombreRed}", new Point3d(xCentro, ySub, 0), txtSub, Estilo.Subtitulo, AttachmentPoint.MiddleCenter);

            double yEsc = ySub - txtSub * Estilo.Interlineado;
            DrawText(ms, tr, $"Escala Horizontal 1:1   ·   Exageración Vertical: {s.ExagVertical:0.#}x",
                new Point3d(xCentro, yEsc, 0), txtPeq, Estilo.Secundario, AttachmentPoint.MiddleCenter);

            double anchoCaja = Math.Min(s.UnidadBase * 24.0, s.AnchoGrid * 0.22);
            double altoCaja = s.AlturaHeader * 0.62;
            double yCajas = s.Origen.Y - s.UnidadBase;
            DrawCajaCota(ms, tr, s, new Point3d(s.Origen.X + s.UnidadBase, yCajas, 0), anchoCaja, altoCaja,
                "COTA INICIAL", nodos[0].Invert);
            DrawCajaCota(ms, tr, s, new Point3d(s.XDer - s.UnidadBase - anchoCaja, yCajas, 0), anchoCaja, altoCaja,
                "COTA FINAL", nodos[nodos.Count - 1].Invert);
        }

        private static void DrawCajaCota(BlockTableRecord ms, Transaction tr, Sistema s, Point3d esqSupIzq,
            double ancho, double alto, string titulo, double valor)
        {
            DrawRectPoly(ms, tr, esqSupIzq, new Point3d(esqSupIzq.X + ancho, esqSupIzq.Y - alto, 0), Estilo.Marco);
            double txtChico = s.UnidadBase * Estilo.PropPequeno;
            double txtGrande = s.UnidadBase * Estilo.PropSubtitulo;
            double xc = esqSupIzq.X + ancho / 2.0;
            DrawText(ms, tr, titulo, new Point3d(xc, esqSupIzq.Y - txtChico * 1.3, 0), txtChico, Estilo.Secundario, AttachmentPoint.TopCenter);
            DrawText(ms, tr, valor.ToString("F2") + " ft", new Point3d(xc, esqSupIzq.Y - alto * 0.55, 0), txtGrande, Estilo.Cota, AttachmentPoint.MiddleCenter);
        }

        private static void DrawBottomTable(BlockTableRecord ms, Transaction tr, Sistema s,
            List<NodoBuzon> nodos, List<TramoPipe> tramos, List<PuntoTerreno> terreno)
        {
            double txt = s.UnidadBase * Estilo.PropPequeno;
            double xEtiquetas = s.Origen.X + s.UnidadBase * 0.6;
            double xIzqDatos = s.Origen.X + s.AnchoEjeY;

            // Divisorias verticales de la tabla, alineadas con la grilla de arriba.
            DrawLine(ms, tr, new Point3d(xIzqDatos, s.YTableTop, 0), new Point3d(xIzqDatos, s.YTableBottom, 0), Estilo.Marco);
            foreach (var n in nodos)
            {
                double x = s.X(n.Station);
                DrawLine(ms, tr, new Point3d(x, s.YTableTop, 0), new Point3d(x, s.YTableBottom, 0), Estilo.Grid);
            }

            double y = s.YTableTop;
            double YCentroFila() => y - s.AlturaFila / 2.0;
            void Divisora()
            {
                y -= s.AlturaFila;
                DrawLine(ms, tr, new Point3d(s.Origen.X, y, 0), new Point3d(s.XDer, y, 0), Estilo.Marco);
            }
            void Etiqueta(string texto) =>
                DrawText(ms, tr, texto, new Point3d(xEtiquetas, YCentroFila(), 0), txt, Estilo.Secundario, AttachmentPoint.MiddleLeft);

            // — PROGRESIVA —
            Etiqueta("PROGRESIVA");
            foreach (var n in nodos)
                DrawText(ms, tr, FormatEstacion(n.Station), new Point3d(s.X(n.Station), YCentroFila(), 0), txt, Estilo.Secundario, AttachmentPoint.MiddleCenter);
            Divisora();

            // — COTA TERRENO —
            if (s.MostrarTerreno)
            {
                Etiqueta("COTA TERRENO (ft)");
                foreach (var n in nodos)
                {
                    var v = InterpolarTerreno(terreno, n.Station);
                    if (v.HasValue)
                        DrawText(ms, tr, v.Value.ToString("F2"), new Point3d(s.X(n.Station), YCentroFila(), 0), txt, Estilo.Terreno, AttachmentPoint.MiddleCenter);
                }
                Divisora();
            }

            // — COTA TAPA —
            if (s.MostrarTapa)
            {
                Etiqueta("COTA TAPA (ft)");
                foreach (var n in nodos)
                {
                    var v = TryRim(n.St);
                    if (v.HasValue)
                        DrawText(ms, tr, v.Value.ToString("F2"), new Point3d(s.X(n.Station), YCentroFila(), 0), txt, Estilo.ValorImportante, AttachmentPoint.MiddleCenter);
                }
                Divisora();
            }

            // — COTA INVERT —
            Etiqueta("COTA INVERT (ft)");
            foreach (var n in nodos)
                DrawText(ms, tr, n.Invert.ToString("F2"), new Point3d(s.X(n.Station), YCentroFila(), 0), txt, Estilo.ValorImportante, AttachmentPoint.MiddleCenter);
            Divisora();

            // — DIÁMETRO — (constante en toda la red: una sola celda; si varía: una por tramo)
            Etiqueta("DIÁMETRO (in)");
            if (s.DiametroConstante)
            {
                string texto = s.DiametroConstanteTexto +
                    (string.IsNullOrWhiteSpace(s.MaterialConstante) ? "" : $" ({s.MaterialConstante})");
                DrawText(ms, tr, texto, new Point3d((xIzqDatos + s.XDer) / 2.0, YCentroFila(), 0), txt, Estilo.Secundario, AttachmentPoint.MiddleCenter);
            }
            else if (tramos != null)
            {
                foreach (var t in tramos)
                {
                    double xm = (s.X(t.StaIni) + s.X(t.StaFin)) / 2.0;
                    string diamTxt = ""; try { diamTxt = FormatoDiametro(t.P); } catch { }
                    DrawText(ms, tr, diamTxt, new Point3d(xm, YCentroFila(), 0), txt, Estilo.Secundario, AttachmentPoint.MiddleCenter);
                }
            }
            Divisora();

            // — LONGITUD —
            Etiqueta("LONGITUD (ft)");
            if (tramos != null)
                foreach (var t in tramos)
                {
                    double xm = (s.X(t.StaIni) + s.X(t.StaFin)) / 2.0;
                    DrawText(ms, tr, (t.StaFin - t.StaIni).ToString("F2"), new Point3d(xm, YCentroFila(), 0), txt, Estilo.Secundario, AttachmentPoint.MiddleCenter);
                }
            Divisora();

            // — PENDIENTE —
            Etiqueta("PENDIENTE (%)");
            if (tramos != null)
                foreach (var t in tramos)
                {
                    double longi = t.StaFin - t.StaIni;
                    double pend = longi > 1e-6 ? (t.InvIni - t.InvFin) / longi * 100.0 : 0.0;
                    double xm = (s.X(t.StaIni) + s.X(t.StaFin)) / 2.0;
                    DrawText(ms, tr, pend.ToString("F2"), new Point3d(xm, YCentroFila(), 0), txt, Estilo.Secundario, AttachmentPoint.MiddleCenter);
                }
            Divisora();
        }

        private static void DrawLegend(BlockTableRecord ms, Transaction tr, Sistema s)
        {
            double xIni = s.XDer + s.UnidadBase * 3.0;
            double ancho = Math.Max(s.UnidadBase * Estilo.PropAnchoLeyenda, s.UnidadBase * 20.0);
            double txt = s.UnidadBase * Estilo.PropPequeno;
            double alturaLinea = txt * 2.2;

            var items = new List<(short color, string texto, bool esLinea)>();
            if (s.MostrarTerreno) items.Add((Estilo.Terreno, "TERRENO NATURAL", true));
            items.Add((Estilo.Tuberia, "TUBERÍA", true));
            items.Add((Estilo.Buzon, "BUZÓN", false));
            items.Add((Estilo.ValorImportante, "C.I. = COTA INVERT", false));
            items.Add((Estilo.ValorImportante, "C.T. = COTA TAPA", false));

            double alto = alturaLinea * (items.Count + 1.6);
            double yTop = s.Origen.Y - s.AlturaHeader;
            DrawRectPoly(ms, tr, new Point3d(xIni, yTop, 0), new Point3d(xIni + ancho, yTop - alto, 0), Estilo.Marco);
            DrawText(ms, tr, "LEYENDA", new Point3d(xIni + ancho / 2.0, yTop - alturaLinea * 0.8, 0),
                txt * 1.15, Estilo.Subtitulo, AttachmentPoint.MiddleCenter);

            double xMuestra0 = xIni + s.UnidadBase * 1.0, xMuestra1 = xIni + s.UnidadBase * 4.0;
            double xTexto = xIni + s.UnidadBase * 5.0;
            double yy = yTop - alturaLinea * 1.8;
            foreach (var (color, texto, esLinea) in items)
            {
                if (esLinea)
                    DrawLine(ms, tr, new Point3d(xMuestra0, yy, 0), new Point3d(xMuestra1, yy, 0), color);
                else
                    DrawRectPoly(ms, tr, new Point3d(xMuestra0 + (xMuestra1 - xMuestra0) * 0.3, yy + txt * 0.4, 0),
                        new Point3d(xMuestra1 - (xMuestra1 - xMuestra0) * 0.3, yy - txt * 0.4, 0), color);
                DrawText(ms, tr, texto, new Point3d(xTexto, yy, 0), txt, Estilo.Secundario, AttachmentPoint.MiddleLeft);
                yy -= alturaLinea;
            }
        }

        // ════════════════════════════════════════════════════════════════════
        //  HELPERS DE BAJO NIVEL (entidades, formato, datos)
        // ════════════════════════════════════════════════════════════════════

        private static void DrawLine(BlockTableRecord ms, Transaction tr, Point3d p1, Point3d p2, short color, string linetype = null)
        {
            var ln = new Line(p1, p2) { Layer = Estilo.Capa, Color = Color.FromColorIndex(ColorMethod.ByAci, color) };
            if (linetype != null) { try { ln.Linetype = linetype; } catch { } }
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

        private static double? TryRim(CivilDB.Structure st)
        {
            try { return st.RimElevation; } catch { return null; }
        }

        private static double? InterpolarTerreno(List<PuntoTerreno> terreno, double station)
        {
            if (terreno == null) return null;
            const double tol = 0.02;
            foreach (var p in terreno)
                if (Math.Abs(p.Station - station) < tol) return p.Elevation;
            for (int i = 0; i < terreno.Count - 1; i++)
            {
                var a = terreno[i]; var b = terreno[i + 1];
                if (station >= a.Station && station <= b.Station && b.Station > a.Station)
                {
                    double f = (station - a.Station) / (b.Station - a.Station);
                    return a.Elevation + (b.Elevation - a.Elevation) * f;
                }
            }
            return null;
        }

        // "0+40.84", igual convención que usa Civil3D nativamente para estaciones.
        private static string FormatEstacion(double sta)
        {
            int whole = (int)Math.Floor(sta / 100.0);
            double rem = sta - whole * 100.0;
            return $"{whole}+{rem:00.00}";
        }

        private static double Clamp(double v, double lo, double hi) => v < lo ? lo : (v > hi ? hi : v);

        // Escoge un paso "lindo" (1/2/5 × 10^n) para las líneas de cota, apuntando
        // a ~lineasObjetivo líneas en el rango dado — evita pasos como "3.17".
        private static double PasoLindo(double rango, int lineasObjetivo)
        {
            if (rango <= 0) rango = 1.0;
            double bruto = rango / Math.Max(1, lineasObjetivo);
            double mag = Math.Pow(10, Math.Floor(Math.Log10(bruto)));
            double norm = bruto / mag;
            double nice = norm < 1.5 ? 1 : norm < 3 ? 2 : norm < 7 ? 5 : 10;
            return nice * mag;
        }

        private static readonly double[] ExagCandidatas = { 1, 2, 5, 10, 20, 50, 100, 200, 500, 1000 };

        // Redondea la exageración vertical al candidato "típico" más cercano
        // (misma familia de valores que usa Civil3D: 5x, 10x, 20x...).
        private static double RedondearExageracion(double bruta)
        {
            double best = ExagCandidatas[0], bestDiff = double.MaxValue;
            foreach (var c in ExagCandidatas)
            {
                double diff = Math.Abs(Math.Log(c) - Math.Log(Math.Max(bruta, 0.01)));
                if (diff < bestDiff) { bestDiff = diff; best = c; }
            }
            return best;
        }
    }
}
