using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text.RegularExpressions;
using Autodesk.AutoCAD.Colors;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.Civil.ApplicationServices;
using Autodesk.Civil.DatabaseServices.Styles;
using CivilDB = Autodesk.Civil.DatabaseServices;
using Exception = System.Exception;

// ============================================================================
//  ESTILOS DEL PERFIL (DISENO.md E, E.1–E.7)
//   · Capas PDFCAD_PERFIL / PDFCAD_PERFIL_EJE, TextStyle PDFCAD_PERFIL,
//     linetype discontinuo (cadena DASHED → TRAZOS → HIDDEN → LÍNEAS_OCULTAS →
//     ACAD_ISO02W100), ProfileViewStyle, band set vacío, estilo de terreno,
//     eje, tubos/estructura para overrides por vista, marcador invisible y
//     juegos de etiquetas vacíos. Los estilos de ETIQUETA están en
//     PerfilEstilosEtiquetas.cs.
//   · Idempotente: si el estilo existe se REAPLICAN sus propiedades; nunca se
//     modifica un estilo cuyos parámetros de nombre no coinciden.
//   · Cada Set va en Set("prop", () => …) que registra [ESTILO] si falla.
// ============================================================================

namespace Civil3DBasico
{
    internal static class PerfilEstilos
    {
        public const string CAPA = "PDFCAD_PERFIL";          // ACI 7
        public const string CAPA_EJE = "PDFCAD_PERFIL_EJE";  // ACI 6
        public const string TEXTSTYLE = "PDFCAD_PERFIL";     // romans.shx
        public const double FACTOR_PL_PIES = 1.0 / 12.0;     // I-1
        public const double FACTOR_PL_METROS = 0.0254;
        private static readonly CultureInfo INV = CultureInfo.InvariantCulture;
        private static readonly Regex TOKEN = new Regex(@"<\[[^\]]*\]>");

        internal static Color Aci(short n) { return Color.FromColorIndex(ColorMethod.ByAci, n); }

        /// <summary>
        /// E.1–E.9 (T1a, y de nuevo en G.7/G.9): asegura capas, TextStyle, linetype y TODOS los estilos (llama a
        /// PerfilEstilosEtiquetas.AsegurarTodos) con V, intervalos y factorPl dados. Devuelve los ids (Null = no disponible, con aviso).
        /// </summary>
        internal static EstilosPerfil Asegurar(Transaction tr, Database db, CivilDocument civDoc, double s, double v, Intervalos intv,
                                               double factorPl, double factorPlInicial)
        {
            var est = new EstilosPerfil { FactorPl = factorPl, SufijoPl = SufijoPl(factorPl, factorPlInicial) };
            est.CapaId = AsegurarCapa(tr, db, CAPA, 7);
            est.CapaEjeId = AsegurarCapa(tr, db, CAPA_EJE, 6);
            AsegurarTextStyle(tr, db);
            est.Linetype = AsegurarLinetype(tr, db, s, out double esc); est.LinetypeEscala = esc;
            var st = civDoc.Styles;
            est.SinMarcador = Intentar("marcador", () => AsegurarMarcador(tr, st, est));
            est.VistaStyle = Intentar("vista", () => AsegurarVistaStyle(tr, civDoc, s, v, intv, est));
            est.BandSetVacio = Intentar("bandas", () => AsegurarBandSet(tr, st));
            est.TerrenoStyle = Intentar("terreno", () => AsegurarTerreno(tr, st, s, est));
            est.LabelSetPerfilVacio = Intentar("juego perfil", () => JuegoVacio(tr, st.LabelSetStyles.ProfileLabelSetStyles, "PDFCAD Perfil Sin etiquetas"));
            est.EjeStyle = Intentar("eje", () => AsegurarEje(tr, st));
            est.LabelSetEjeVacio = Intentar("juego eje", () => JuegoVacio(tr, st.LabelSetStyles.AlignmentLabelSetStyles, "PDFCAD Perfil Sin etiquetas"));
            var colPres = StylesRootPressurePipesExtension.GetPressurePipeStyles(st);
            string sTxt = s.ToString("G", INV);
            est.TuboGrav = Intentar("tubo", () => TuboGrav(tr, st.PipeStyles, "PDFCAD Perfil Tubo", 0, est));
            est.TuboGravAband = Intentar("tubo aband", () => TuboGrav(tr, st.PipeStyles, "PDFCAD Perfil Tubo Abandonado S" + sTxt, 1, est));
            est.CruceGrav = Intentar("cruce", () => TuboGrav(tr, st.PipeStyles, "PDFCAD Perfil Cruce", 2, est));
            est.TuboPres = Intentar("tubo pres", () => TuboPres(tr, colPres, "PDFCAD Perfil Tubo", 0, est));
            est.TuboPresAband = Intentar("tubo pres aband", () => TuboPres(tr, colPres, "PDFCAD Perfil Tubo Abandonado S" + sTxt, 1, est));
            est.CrucePres = Intentar("cruce pres", () => TuboPres(tr, colPres, "PDFCAD Perfil Cruce", 2, est));
            est.Estructura = Intentar("estructura", () => AsegurarEstructura(tr, st));
            PerfilEstilosEtiquetas.AsegurarTodos(tr, civDoc, est);
            return est;
        }

        private static ObjectId Intentar(string que, Func<ObjectId> f)
        {
            try { return f(); }
            catch (Exception ex) { PerfilLog.Error("ESTILO", que, ex); PerfilLog.Aviso("Estilo no disponible: " + que); return ObjectId.Null; }
        }

        // ------------------------------------------------------------ E.2 vista

        /// <summary>E.2: asegura (o reutiliza) el ProfileViewStyle "PDFCAD Perfil VE{VE} E{CotaMayor}-{CotaMenor} S{EstMayor}{SufijoPl}".</summary>
        internal static ObjectId AsegurarVistaStyle(Transaction tr, CivilDocument civDoc, double s, double v, Intervalos intv, EstilosPerfil est)
        {
            double ve = s / v;
            string nombre = NombreVistaStyle(ve, intv, est.SufijoPl);
            ObjectId id = Asegurar(civDoc.Styles.ProfileViewStyles, nombre, tr, out _);
            var pvs = (ProfileViewStyle)tr.GetObject(id, OpenMode.ForWrite);
            double f = est.FactorPl;
            foreach (var (eje, ax) in new[] { ("inferior", pvs.BottomAxis), ("izquierdo", pvs.LeftAxis), ("derecho", pvs.RightAxis) })
            {
                string lt = ""; try { lt = ax.MajorTickStyle.LabelText; } catch { }
                PerfilLog.Log("ESTILO", $"LabelText eje {eje}: {lt}");
                string sin = TOKEN.Replace(lt ?? "", "");
                if (Regex.IsMatch(sin, @"\p{L}"))
                {
                    string solo = PerfilEstilosEtiquetas.SoloTokens(lt);
                    if (solo.Length > 0) { Set(nombre, "LabelText " + eje, () => ax.MajorTickStyle.LabelText = solo); PerfilLog.Log("ESTILO", "LabelText saneado: " + solo); }
                }
            }
            Set(nombre, "VE", () => pvs.GraphStyle.VerticalExaggeration = ve);
            Set(nombre, "Direction", () => pvs.GraphStyle.Direction = GraphDirectionType.LeftToRight);
            Set(nombre, "GraphTitle", () => pvs.GraphStyle.TitleStyle.Text = "");
            var g = pvs.GridStyle;
            Set(nombre, "GridPadding", () => { g.GridPaddingAbove = 0; g.GridPaddingBottom = 0; g.GridPaddingLeft = 0; g.GridPaddingRight = 0; });
            Set(nombre, "AxisOffset", () => { g.AxisOffsetAbove = 0; g.AxisOffsetBottom = 0; g.AxisOffsetLeft = 0; g.AxisOffsetRight = 0; });
            foreach (var go in new[] { g.HorizontalGridOptions, g.VerticalGridOptions })
                Set(nombre, "GridOptions", () => { go.UseClipGrid = false; go.ClipToHighestProfile = false; go.OmitGridInPaddingAreas = true; });
            void Eje(AxisStyle ax, string que, bool mostrar, double mayor, double menor, string titulo, bool tituloCentro)
            {
                Set(nombre, que + ".Show", () => ax.ShowTickAndLabel = mostrar);
                Set(nombre, que + ".Major", () => { ax.MajorTickStyle.Interval = mayor; ax.MajorTickStyle.TextHeight = Pl(0.10, f); ax.MajorTickStyle.Size = Pl(0.05, f); ax.MajorTickStyle.TextStyle = TEXTSTYLE; });
                Set(nombre, que + ".Minor", () => ax.MinorTickStyle.Interval = menor);
                Set(nombre, que + ".Title", () =>
                {
                    ax.TitleStyle.Text = titulo;
                    if (titulo.Length > 0) { ax.TitleStyle.TextHeight = Pl(0.10, f); ax.TitleStyle.TextStyle = TEXTSTYLE; }
                    if (tituloCentro) ax.TitleStyle.Location = AxisTitleLocationType.Center;
                });
            }
            Eje(pvs.BottomAxis, "BottomAxis", true, intv.EstMayor, intv.EstMenor, "", false);
            Eje(pvs.TopAxis, "TopAxis", false, intv.EstMayor, intv.EstMenor, "", false);
            Eje(pvs.LeftAxis, "LeftAxis", true, intv.CotaMayor, intv.CotaMenor, PerfilTextos.TITULO_ELEVACION, true);
            Eje(pvs.RightAxis, "RightAxis", true, intv.CotaMayor, intv.CotaMenor, PerfilTextos.TITULO_ELEVACION, true);
            void Vis(ProfileViewDisplayStyleType t, bool vis, short color = 7, LineWeight lw = LineWeight.ByLayer, bool continuo = false)
            {
                Set(nombre, t.ToString(), () =>
                {
                    var d = pvs.GetDisplayStylePlan(t);
                    d.Visible = vis;
                    if (!vis) return;
                    d.Color = Aci(color); if (lw != LineWeight.ByLayer) d.Lineweight = lw;
                    if (continuo) d.Linetype = "Continuous";
                });
            }
            foreach (var t in new[] { ProfileViewDisplayStyleType.LeftAxis, ProfileViewDisplayStyleType.RightAxis, ProfileViewDisplayStyleType.BottomAxis, ProfileViewDisplayStyleType.TopAxis })
                Vis(t, true, 7, LineWeight.LineWeight050, true);
            foreach (var t in new[] { ProfileViewDisplayStyleType.LeftAxisTitle, ProfileViewDisplayStyleType.RightAxisTitle,
                                      ProfileViewDisplayStyleType.LeftAxisAnnotationMajor, ProfileViewDisplayStyleType.RightAxisAnnotationMajor,
                                      ProfileViewDisplayStyleType.BottomAxisAnnotationMajor })
                Vis(t, true, 7, LineWeight.LineWeight018);
            foreach (var t in new[] { ProfileViewDisplayStyleType.LeftAxisTicksMajor, ProfileViewDisplayStyleType.RightAxisTicksMajor, ProfileViewDisplayStyleType.BottomAxisTicksMajor })
                Vis(t, true, 7, LineWeight.LineWeight025, true);
            Vis(ProfileViewDisplayStyleType.GridHorizontalMajor, true, 7, LineWeight.LineWeight035, true);
            Vis(ProfileViewDisplayStyleType.GridHorizontalMinor, true, 253, LineWeight.LineWeight013, true);
            Vis(ProfileViewDisplayStyleType.GridVerticalMajor, true, 7, LineWeight.LineWeight025, true);
            foreach (var t in new[] { ProfileViewDisplayStyleType.GraphTitle, ProfileViewDisplayStyleType.BottomAxisTitle, ProfileViewDisplayStyleType.TopAxisTitle,
                                      ProfileViewDisplayStyleType.TopAxisAnnotationMajor, ProfileViewDisplayStyleType.TopAxisAnnotationMinor,
                                      ProfileViewDisplayStyleType.TopAxisTicksMajor, ProfileViewDisplayStyleType.TopAxisTicksMinor,
                                      ProfileViewDisplayStyleType.LeftAxisAnnotationMinor, ProfileViewDisplayStyleType.RightAxisAnnotationMinor,
                                      ProfileViewDisplayStyleType.BottomAxisAnnotationMinor, ProfileViewDisplayStyleType.LeftAxisTicksMinor,
                                      ProfileViewDisplayStyleType.RightAxisTicksMinor, ProfileViewDisplayStyleType.BottomAxisTicksMinor,
                                      ProfileViewDisplayStyleType.GridVerticalMinor, ProfileViewDisplayStyleType.GridAtHGP,
                                      ProfileViewDisplayStyleType.TopAxisAnnotationHGP, ProfileViewDisplayStyleType.BottomAxisAnnotationHGP,
                                      ProfileViewDisplayStyleType.TopAxisTicksHGP, ProfileViewDisplayStyleType.BottomAxisTicksHGP,
                                      ProfileViewDisplayStyleType.GridAtSampleLineStations, ProfileViewDisplayStyleType.ProfileHatch })
                Vis(t, false);
            return id;
        }

        /// <summary>E.2: nombre del ProfileViewStyle con números en "G" invariante.</summary>
        internal static string NombreVistaStyle(double ve, Intervalos intv, string sufijoPl)
        {
            return "PDFCAD Perfil VE" + Math.Round(ve, 4).ToString("G", INV) + " E" + intv.CotaMayor.ToString("G", INV) + "-" + intv.CotaMenor.ToString("G", INV)
                   + " S" + intv.EstMayor.ToString("G", INV) + (sufijoPl ?? "");
        }

        // ------------------------------------------------------------ E.3 – E.7

        private static ObjectId AsegurarBandSet(Transaction tr, StylesRoot st)
        {
            const string n = "PDFCAD Perfil Sin bandas";
            var col = st.ProfileViewBandSetStyles;
            return col.Contains(n) ? col[n] : col.Add(n);
        }

        private static ObjectId AsegurarTerreno(Transaction tr, StylesRoot st, double s, EstilosPerfil est)
        {
            string nombre = "PDFCAD Perfil Terreno S" + s.ToString("G", INV);
            ObjectId id = Asegurar(st.ProfileStyles, nombre, tr, out _);
            var ps = (ProfileStyle)tr.GetObject(id, OpenMode.ForWrite);
            foreach (var t in new[] { ProfileDisplayStyleProfileType.Line, ProfileDisplayStyleProfileType.Curve,
                                      ProfileDisplayStyleProfileType.SymmetricalParabola, ProfileDisplayStyleProfileType.AsymmetricalParabola })
                Set(nombre, t.ToString(), () =>
                {
                    var d = ps.GetDisplayStyleProfile(t);
                    d.Visible = true; d.Color = Aci(8); d.Lineweight = LineWeight.LineWeight025;
                    d.Linetype = est.Linetype; d.LinetypeScale = est.LinetypeEscala;
                });
            foreach (var t in new[] { ProfileDisplayStyleProfileType.Arrow, ProfileDisplayStyleProfileType.LineExtension,
                                      ProfileDisplayStyleProfileType.ParabolicCurveExtension, ProfileDisplayStyleProfileType.WarningSymbol })
                Set(nombre, t.ToString(), () => ps.GetDisplayStyleProfile(t).Visible = false);
            if (!est.SinMarcador.IsNull)
                foreach (var pi in typeof(ProfileStyle).GetProperties())
                    if (pi.PropertyType == typeof(ObjectId) && pi.CanWrite && pi.Name.EndsWith("MarkerStyle", StringComparison.Ordinal))
                        Set(nombre, pi.Name, () => pi.SetValue(ps, est.SinMarcador));
            return id;
        }

        private static ObjectId JuegoVacio(Transaction tr, StyleCollectionBase col, string nombre)
        {
            ObjectId id = col.Contains(nombre) ? col[nombre] : col.Add(nombre);
            var js = (BaseLabelSetStyle)tr.GetObject(id, OpenMode.ForWrite);
            for (int guard = 0; js.Count > 0 && guard < 500; guard++) js.RemoveAt(js.Count - 1);
            return id;
        }

        private static ObjectId AsegurarEje(Transaction tr, StylesRoot st)
        {
            const string nombre = "PDFCAD Perfil Eje";
            ObjectId id = Asegurar(st.AlignmentStyles, nombre, tr, out _);
            var a = (AlignmentStyle)tr.GetObject(id, OpenMode.ForWrite);
            foreach (var t in new[] { AlignmentDisplayStyleType.Line, AlignmentDisplayStyleType.Curve, AlignmentDisplayStyleType.Spiral })
                Set(nombre, t.ToString(), () => { var d = a.GetDisplayStylePlan(t); d.Visible = true; d.Color = Aci(6); d.Lineweight = LineWeight.LineWeight018; });
            foreach (var t in new[] { AlignmentDisplayStyleType.Arrow, AlignmentDisplayStyleType.LineExtensions, AlignmentDisplayStyleType.CurveExtensions,
                                      AlignmentDisplayStyleType.TangentExtensions, AlignmentDisplayStyleType.WarningSymbol })
                Set(nombre, t.ToString(), () => a.GetDisplayStylePlan(t).Visible = false);
            return id;
        }

        /// <summary>E.6 gravedad. tipo 0 = recorrido, 1 = abandonado (discontinuo), 2 = cruce.</summary>
        private static ObjectId TuboGrav(Transaction tr, StyleCollectionBase col, string nombre, int tipo, EstilosPerfil est)
        {
            ObjectId id = Asegurar(col, nombre, tr, out _);
            var ps = (PipeStyle)tr.GetObject(id, OpenMode.ForWrite);
            void D(PipeDisplayStyleProfileType t, bool vis, short c = 7, LineWeight lw = LineWeight.LineWeight025, bool disc = false)
            {
                Set(nombre, t.ToString(), () =>
                {
                    var d = ps.GetDisplayStyleProfile(t); d.Visible = vis;
                    if (!vis) return;
                    d.Color = Aci(c); d.Lineweight = lw;
                    d.Linetype = disc ? est.Linetype : "Continuous"; if (disc) d.LinetypeScale = est.LinetypeEscala;
                });
            }
            if (tipo == 0) { D(PipeDisplayStyleProfileType.OutsideWalls, true, 7, LineWeight.LineWeight050); D(PipeDisplayStyleProfileType.EndLine, true, 7, LineWeight.LineWeight025); D(PipeDisplayStyleProfileType.CrossingPipeOutsideWall, true, 7, LineWeight.LineWeight035); }
            else if (tipo == 1) { D(PipeDisplayStyleProfileType.OutsideWalls, true, 7, LineWeight.LineWeight025, true); D(PipeDisplayStyleProfileType.EndLine, true, 7, LineWeight.LineWeight018); D(PipeDisplayStyleProfileType.CrossingPipeOutsideWall, true, 7, LineWeight.LineWeight025, true); }
            else { D(PipeDisplayStyleProfileType.CrossingPipeOutsideWall, true, 7, LineWeight.LineWeight035); D(PipeDisplayStyleProfileType.OutsideWalls, true, 8, LineWeight.LineWeight025); D(PipeDisplayStyleProfileType.EndLine, true, 8, LineWeight.LineWeight018); }
            foreach (var t in new[] { PipeDisplayStyleProfileType.Centerline, PipeDisplayStyleProfileType.InsideWalls, PipeDisplayStyleProfileType.Hatch,
                                      PipeDisplayStyleProfileType.CrossingPipeInsideWall, PipeDisplayStyleProfileType.CrossingPipeHatch,
                                      PipeDisplayStyleProfileType.HydraulicGradeLine, PipeDisplayStyleProfileType.EnergyGradeLine })
                D(t, false);
            Set(nombre, "ProfileOption", () => { ps.ProfileOption.WallSizeType = PipeWallSizeType.UsePartDimensions; ps.ProfileOption.EndSizeType = PipeEndSizeType.DrawToOuterWall; });
            return id;
        }

        /// <summary>E.6 presión (mismo criterio que TuboGrav).</summary>
        private static ObjectId TuboPres(Transaction tr, StyleCollectionBase col, string nombre, int tipo, EstilosPerfil est)
        {
            ObjectId id = Asegurar(col, nombre, tr, out _);
            var ps = (PressurePipeStyle)tr.GetObject(id, OpenMode.ForWrite);
            void D(PressurePipeDisplayStyleProfileType t, bool vis, short c = 7, LineWeight lw = LineWeight.LineWeight025, bool disc = false)
            {
                Set(nombre, t.ToString(), () =>
                {
                    var d = ps.GetDisplayStyleProfile(t); d.Visible = vis;
                    if (!vis) return;
                    d.Color = Aci(c); d.Lineweight = lw;
                    d.Linetype = disc ? est.Linetype : "Continuous"; if (disc) d.LinetypeScale = est.LinetypeEscala;
                });
            }
            if (tipo == 0) { D(PressurePipeDisplayStyleProfileType.OutsideWalls, true, 7, LineWeight.LineWeight050); D(PressurePipeDisplayStyleProfileType.EndLine, true, 7, LineWeight.LineWeight025); D(PressurePipeDisplayStyleProfileType.CrossingPipeOutsideWall, true, 7, LineWeight.LineWeight035); }
            else if (tipo == 1) { D(PressurePipeDisplayStyleProfileType.OutsideWalls, true, 7, LineWeight.LineWeight025, true); D(PressurePipeDisplayStyleProfileType.EndLine, true, 7, LineWeight.LineWeight018); D(PressurePipeDisplayStyleProfileType.CrossingPipeOutsideWall, true, 7, LineWeight.LineWeight025, true); }
            else { D(PressurePipeDisplayStyleProfileType.CrossingPipeOutsideWall, true, 7, LineWeight.LineWeight035); D(PressurePipeDisplayStyleProfileType.OutsideWalls, true, 8, LineWeight.LineWeight025); D(PressurePipeDisplayStyleProfileType.EndLine, true, 8, LineWeight.LineWeight018); }
            foreach (var t in new[] { PressurePipeDisplayStyleProfileType.Centerline, PressurePipeDisplayStyleProfileType.InsideWalls, PressurePipeDisplayStyleProfileType.Hatch,
                                      PressurePipeDisplayStyleProfileType.CrossingPipeInsideWall, PressurePipeDisplayStyleProfileType.CrossingPipeHatch })
                D(t, false);
            Set(nombre, "ProfileOption", () => { ps.ProfileOption.WallSizeType = PressurePipeWallSizeType.UsePartDimensions; ps.ProfileOption.EndSizeType = PressurePipeEndSizeType.DrawToOuterWall; });
            return id;
        }

        private static ObjectId AsegurarEstructura(Transaction tr, StylesRoot st)
        {
            const string nombre = "PDFCAD Perfil Estructura";
            ObjectId id = Asegurar(st.StructureStyles, nombre, tr, out _);
            var ss = (StructureStyle)tr.GetObject(id, OpenMode.ForWrite);
            Set(nombre, "Structure", () => { var d = ss.GetDisplayStyleProfile(StructureDisplayStyleProfileType.Structure); d.Visible = true; d.Color = Aci(7); d.Lineweight = LineWeight.LineWeight035; });
            Set(nombre, "StructureHatch", () => ss.GetDisplayStyleProfile(StructureDisplayStyleProfileType.StructureHatch).Visible = false);
            Set(nombre, "StructurePipeOutlines", () => ss.GetDisplayStyleProfile(StructureDisplayStyleProfileType.StructurePipeOutlines).Visible = false);
            Set(nombre, "ProfileOption", () => { ss.ProfileOption.ViewOptions = StructureViewType.DisplayAsBoundary; ss.ProfileOption.MaskConnectedObjects = false; });
            return id;
        }

        private static ObjectId AsegurarMarcador(Transaction tr, StylesRoot st, EstilosPerfil est)
        {
            const string nombre = "PDFCAD Perfil Sin marcador";
            var col = st.MarkerStyles;
            ObjectId id = col.Contains(nombre) ? col[nombre] : col.Add(nombre);
            var m = (MarkerStyle)tr.GetObject(id, OpenMode.ForWrite);
            Set(nombre, "Tipo", () => { m.MarkerType = MarkerDisplayType.UseCustomMarker; m.CustomMarkerStyle = CustomMarkerType.CustomMarkerBlank; m.CustomMarkerSuperimposeStyle = CustomMarkerSuperimposeType.None; });
            Set(nombre, "Tamaño", () => { m.SizeType = MarkerSizeType.DrawingScale; m.MarkerSize = Pl(0.01, est.FactorPl); });
            Set(nombre, "Plan", () => m.GetMarkerDisplayStylePlan().Visible = false);
            Set(nombre, "Model", () => m.GetMarkerDisplayStyleModel().Visible = false);
            Set(nombre, "Profile", () => m.GetMarkerDisplayStyleProfile().Visible = false);
            Set(nombre, "Section", () => m.GetMarkerDisplayStyleSection().Visible = false);
            return id;
        }

        // ------------------------------------------------------------ helpers

        /// <summary>
        /// Helper E: col[nombre] si existe; si no CopyAsSibling del primer estilo cuyo Name no empieza por "PDFCAD";
        /// si no hay base, col.Add(nombre). nuevo = true si se creó.
        /// </summary>
        internal static ObjectId Asegurar(StyleCollectionBase col, string nombre, Transaction tr, out bool nuevo)
        {
            nuevo = false;
            if (col.Contains(nombre)) return col[nombre];
            nuevo = true;
            ObjectId b = PrimeraBase(col, tr);
            if (!b.IsNull)
                try { return ((StyleBase)tr.GetObject(b, OpenMode.ForRead)).CopyAsSibling(nombre); }
                catch (Exception ex) { PerfilLog.Log("ESTILO", "CopyAsSibling " + nombre + ": " + ex.Message + " → Add"); }
            return col.Add(nombre);
        }

        /// <summary>Primer estilo de la colección cuyo Name NO empieza por "PDFCAD" (base de CopyAsSibling y del diagnóstico); Null si no hay.</summary>
        internal static ObjectId PrimeraBase(StyleCollectionBase col, Transaction tr)
        {
            try
            {
                foreach (ObjectId id in col)
                    try { if (!((StyleBase)tr.GetObject(id, OpenMode.ForRead)).Name.StartsWith("PDFCAD", StringComparison.OrdinalIgnoreCase)) return id; } catch { }
            }
            catch { }
            return ObjectId.Null;
        }

        /// <summary>Ejecuta un set de propiedad en try y registra «[ESTILO] estilo.prop: msg» si falla.</summary>
        internal static void Set(string estilo, string prop, Action accion)
        {
            try { accion(); }
            catch (Exception ex) { PerfilLog.Log("ESTILO", estilo + "." + prop + ": " + ex.Message); }
        }

        /// <summary>Pl(d) = d·factorPl: valor de estilo para d pulgadas de ploteo.</summary>
        internal static double Pl(double pulgadas, double factorPl) { return pulgadas * factorPl; }

        /// <summary>"" si factorPl == inicial; si no " P" + factorPl.ToString("G4", invariante). E.</summary>
        internal static string SufijoPl(double factorPl, double factorPlInicial)
        {
            return Math.Abs(factorPl - factorPlInicial) < 1e-12 ? "" : " P" + factorPl.ToString("G4", INV);
        }

        /// <summary>
        /// I-1: FactorPl inicial (1/12 en pies; 0.0254 en metros) con autodetección por BottomAxis.MajorTickStyle.TextHeight
        /// de la base de fábrica (0.004–0.03 → 1/12; 0.05–0.5 → 1). <paramref name="origen"/> describe la decisión para el log.
        /// </summary>
        internal static double FactorPlInicial(Transaction tr, CivilDocument civDoc, bool metros, out string origen)
        {
            double f = metros ? FACTOR_PL_METROS : FACTOR_PL_PIES;
            origen = metros ? "metros (0.0254)" : "pies (1/12)";
            try
            {
                ObjectId b = PrimeraBase(civDoc.Styles.ProfileViewStyles, tr);
                if (!b.IsNull)
                {
                    double hf = ((ProfileViewStyle)tr.GetObject(b, OpenMode.ForRead)).BottomAxis.MajorTickStyle.TextHeight;
                    if (hf >= 0.004 && hf <= 0.03) { f = FACTOR_PL_PIES; origen = $"fábrica hf={hf:G4} → 1/12"; }
                    else if (hf >= 0.05 && hf <= 0.5) { f = 1.0; origen = $"fábrica hf={hf:G4} → 1"; }
                    else origen += $" (fábrica hf={hf:G4} sin decidir)";
                }
            }
            catch (Exception ex) { origen += " (sin base: " + ex.Message + ")"; }
            return f;
        }

        /// <summary>E.1: capa con color ACI (LayerTable ForWrite para Add); si existe, la descongela y desbloquea.</summary>
        internal static ObjectId AsegurarCapa(Transaction tr, Database db, string nombre, short aci)
        {
            try
            {
                var lt = (LayerTable)tr.GetObject(db.LayerTableId, OpenMode.ForRead);
                if (lt.Has(nombre))
                {
                    ObjectId id = lt[nombre];
                    var r = (LayerTableRecord)tr.GetObject(id, OpenMode.ForWrite);
                    if (r.IsFrozen) r.IsFrozen = false;
                    if (r.IsLocked) r.IsLocked = false;
                    return id;
                }
                lt.UpgradeOpen();
                var nuevo = new LayerTableRecord { Name = nombre, Color = Aci(aci) };
                ObjectId nid = lt.Add(nuevo);
                tr.AddNewlyCreatedDBObject(nuevo, true);
                return nid;
            }
            catch (Exception ex) { PerfilLog.Error("ESTILO", "capa " + nombre, ex); return db.Clayer; }
        }

        /// <summary>E.1: TextStyle PDFCAD_PERFIL (romans.shx, TextSize 0, XScale 1); si existe se deja como está.</summary>
        internal static ObjectId AsegurarTextStyle(Transaction tr, Database db)
        {
            try
            {
                var tt = (TextStyleTable)tr.GetObject(db.TextStyleTableId, OpenMode.ForRead);
                if (tt.Has(TEXTSTYLE)) return tt[TEXTSTYLE];
                tt.UpgradeOpen();
                var r = new TextStyleTableRecord { Name = TEXTSTYLE, FileName = "romans.shx", TextSize = 0, XScale = 1.0 };
                ObjectId id = tt.Add(r);
                tr.AddNewlyCreatedDBObject(r, true);
                return id;
            }
            catch (Exception ex) { PerfilLog.Error("ESTILO", "TextStyle", ex); return db.Textstyle; }
        }

        /// <summary>E.1: primer linetype discontinuo disponible (carga de acad.lin / acadiso.lin); escala = 0.25·s/(g·Ltscale). "Continuous" con aviso si ninguno.</summary>
        internal static string AsegurarLinetype(Transaction tr, Database db, double s, out double escala)
        {
            escala = 1.0;
            var cand = new[] { ("DASHED", 0.5), ("TRAZOS", 0.5), ("HIDDEN", 0.25), ("LÍNEAS_OCULTAS", 0.25), ("ACAD_ISO02W100", 12.0) };
            try
            {
                var lt = (LinetypeTable)tr.GetObject(db.LinetypeTableId, OpenMode.ForRead);
                foreach (var (n, g) in cand)
                {
                    if (!lt.Has(n))
                    {
                        foreach (string f in new[] { "acad.lin", "acadiso.lin" })
                        {
                            try { db.LoadLineTypeFile(n, f); } catch { }
                            if (lt.Has(n)) break;
                        }
                    }
                    if (!lt.Has(n)) continue;
                    double lts = db.Ltscale > 0 ? db.Ltscale : 1.0;
                    escala = 0.25 * s / (g * lts);
                    PerfilLog.Log("ESTILO", $"linetype discontinuo {n} escala {escala:G4}");
                    return n;
                }
            }
            catch (Exception ex) { PerfilLog.Error("ESTILO", "linetype", ex); }
            PerfilLog.Aviso("ESTILO", "No hay linetype discontinuo: terreno y abandonados en continuo");
            return "Continuous";
        }
    }
}
