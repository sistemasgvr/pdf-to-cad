using System;
using System.Collections.Generic;
using System.Text.RegularExpressions;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.Civil;
using Autodesk.Civil.ApplicationServices;
using Autodesk.Civil.DatabaseServices.Styles;
using Autodesk.Civil.Settings;
using CivilDB = Autodesk.Civil.DatabaseServices;
using Exception = System.Exception;

// ============================================================================
//  ESTILOS DE ETIQUETA DEL PERFIL (DISENO.md E.8, E.9, E.10)
//   · AsegurarEstiloTexto: estilo con UN componente de texto "PDFCAD_TEXTO"
//     (purga SIEMPRE el resto), leader recto, DraggedStateComponents Composed.
//     El texto real va por etiqueta con SetTextComponentOverride.
//   · Profundidad (solo tokens <[...]>, sin literales) y Límite (sin texto).
//   · Diagnóstico de fábrica al log (E.10).
// ============================================================================

namespace Civil3DBasico
{
    /// <summary>Configuración de un estilo de etiqueta de texto (E.8).</summary>
    internal sealed class ConfigTexto
    {
        public bool Vertical; public LabelTextAttachmentType Attachment; public double AltoIn = 0.12;
        public bool Leader = true; public bool JustificarLeader = true;
    }

    internal static class PerfilEstilosEtiquetas
    {
        public const string COMPONENTE = "PDFCAD_TEXTO";
        public const bool JUSTIFICAR_LEADER_VERTICAL = true;   // I-19: cambiar aquí si la prueba de humo lo desmiente
        private static readonly Regex TOKEN = new Regex(@"<\[[^\]]*\]>");

        private static ConfigTexto Vert(double alto = 0.12) { return new ConfigTexto { Vertical = true, Attachment = LabelTextAttachmentType.MiddleLeft, AltoIn = alto, Leader = true, JustificarLeader = JUSTIFICAR_LEADER_VERTICAL }; }
        private static ConfigTexto Hor(LabelTextAttachmentType at, double alto, bool leader) { return new ConfigTexto { Vertical = false, Attachment = at, AltoIn = alto, Leader = leader, JustificarLeader = false }; }

        /// <summary>
        /// E.8 + E.9: asegura todos los estilos de etiqueta (Callout Sup/Inf, Rasante, Tramo, Titulo, Estacion Extremo, Eje Titulo,
        /// Cruce gravedad/presión, Profundidad, Limite), con est.SufijoPl en el nombre, y rellena sus ids en <paramref name="est"/>.
        /// </summary>
        internal static void AsegurarTodos(Transaction tr, CivilDocument civDoc, EstilosPerfil est)
        {
            var ls = civDoc.Styles.LabelStyles;
            string sf = est.SufijoPl ?? "";
            LabelStyleCollection sel = null, cg = null, cp = null;
            try { sel = ls.ProfileViewLabelStyles.StationElevationLabelStyles; } catch (Exception ex) { PerfilLog.Error("ESTILO", "StationElevationLabelStyles", ex); }
            try { cg = ls.PipeLabelStyles.CrossProfileLabelStyles; } catch (Exception ex) { PerfilLog.Error("ESTILO", "CrossProfileLabelStyles", ex); }
            try { cp = LabelStylesRootPressurePipesExtension.GetPressurePipeLabelStyles(ls).CrossingProfileLabelStyles; } catch (Exception ex) { PerfilLog.Error("ESTILO", "CrossingProfileLabelStyles", ex); }
            if (sel != null)
            {
                est.CalloutSup = AsegurarEstiloTexto(sel, "PDFCAD Perfil Callout Sup" + sf, tr, Vert(), est);
                est.CalloutInf = AsegurarEstiloTexto(sel, "PDFCAD Perfil Callout Inf" + sf, tr, Vert(), est);
                est.Rasante = AsegurarEstiloTexto(sel, "PDFCAD Perfil Rasante" + sf, tr, Vert(), est);
                est.Tramo = AsegurarEstiloTexto(sel, "PDFCAD Perfil Tramo" + sf, tr, Hor(LabelTextAttachmentType.BottomCenter, 0.12, true), est);
                est.Titulo = AsegurarEstiloTexto(sel, "PDFCAD Perfil Titulo" + sf, tr, Hor(LabelTextAttachmentType.TopLeft, 0.20, false), est);
                est.EstExtremo = AsegurarEstiloTexto(sel, "PDFCAD Perfil Estacion Extremo" + sf, tr, Hor(LabelTextAttachmentType.BottomCenter, 0.10, false), est);
                est.EjeTitulo = AsegurarEstiloTexto(sel, "PDFCAD Perfil Eje Titulo" + sf, tr, Hor(LabelTextAttachmentType.TopCenter, 0.10, false), est);
            }
            if (cg != null) est.CruceGravLbl = AsegurarEstiloTexto(cg, "PDFCAD Perfil Cruce" + sf, tr, Vert(), est);
            if (cp != null) est.CrucePresLbl = AsegurarEstiloTexto(cp, "PDFCAD Perfil Cruce" + sf, tr, Vert(), est);
            est.Profundidad = AsegurarProfundidad(tr, civDoc, est);
            est.Limite = AsegurarLimite(tr, civDoc, est);
        }

        /// <summary>E.8: estilo de texto "PDFCAD_TEXTO" en la colección (Asegurar + purga + componente + Properties). Null si falla.</summary>
        internal static ObjectId AsegurarEstiloTexto(LabelStyleCollection col, string nombre, Transaction tr, ConfigTexto cfg, EstilosPerfil est)
        {
            try
            {
                ObjectId id = PerfilEstilos.Asegurar(col, nombre, tr, out bool nuevo);
                var ls = (LabelStyle)tr.GetObject(id, OpenMode.ForWrite);
                PurgarComponentes(ls, tr, COMPONENTE);
                ObjectId cid = Componente(ls, tr, COMPONENTE, LabelStyleComponentType.Text);
                if (cid.IsNull) cid = ls.AddComponent(COMPONENTE, LabelStyleComponentType.Text);
                double f = est.FactorPl;
                var c = (LabelStyleTextComponent)tr.GetObject(cid, OpenMode.ForWrite);
                void S(string p, Action a) { PerfilEstilos.Set(nombre, p, a); }
                S("General.Visible", () => c.General.Visible.Value = true);
                S("Contents", () => c.Text.Contents.Value = "X");
                S("Height", () => c.Text.Height.Value = PerfilEstilos.Pl(cfg.AltoIn, f));
                S("Angle", () => c.Text.Angle.Value = cfg.Vertical ? Math.PI / 2.0 : 0.0);
                S("Attachment", () => c.Text.Attachment.Value = cfg.Attachment);
                S("Offsets", () => { c.Text.XOffset.Value = 0; c.Text.YOffset.Value = 0; c.Text.MaxWidth.Value = 0; });
                S("Color", () => c.Text.Color.Value = PerfilEstilos.Aci(7));
                S("Border", () => { c.Border.Visible.Value = false; c.Border.BackgroundMask.Value = true; c.Border.Gap.Value = PerfilEstilos.Pl(0.02, f); });
                var pr = ls.Properties;
                S("Label", () => { pr.Label.TextStyle.Value = PerfilEstilos.TEXTSTYLE; pr.Label.Layer.Value = PerfilEstilos.CAPA; pr.Label.Visibility.Value = true; });
                S("Orientation", () => pr.Behavior.OrientationReference.Value = OrientationReferenceType.View);
                S("PlanReadable", () => pr.PlanReadability.PlanReadable.Value = false);
                S("Leader", () =>
                {
                    pr.Leader.Visibility.Value = cfg.Leader;
                    pr.Leader.ArrowheadSize.Value = PerfilEstilos.Pl(0.08, f);
                    pr.Leader.Shape.Value = LeaderShapeType.Straight;
                    pr.Leader.Lineweight.Value = LineWeight.LineWeight018;
                    pr.Leader.Color.Value = PerfilEstilos.Aci(7);
                });
                if (nuevo && string.IsNullOrWhiteSpace(pr.Leader.ArrowheadStyle.Value))
                    S("ArrowheadStyle", () =>
                    {
                        ObjectId b = PerfilEstilos.PrimeraBase(col, tr);
                        if (!b.IsNull) pr.Leader.ArrowheadStyle.Value = ((LabelStyle)tr.GetObject(b, OpenMode.ForRead)).Properties.Leader.ArrowheadStyle.Value;
                    });
                S("Dragged", () =>
                {
                    var d = pr.DraggedStateComponents;
                    d.DisplayType.Value = LabelContentDisplayType.Composed;
                    d.BorderVisibility.Value = false; d.UseBackgroundMask.Value = true;
                    d.Gap.Value = PerfilEstilos.Pl(0.02, f); d.TextHeight.Value = PerfilEstilos.Pl(cfg.AltoIn, f); d.MaxTextWidth.Value = 0;
                    d.LeaderAttachment.Value = LeaderAttachmentType.LeaderMiddleOfTopLine;
                    d.LeaderJustification.Value = cfg.JustificarLeader;
                });
                return id;
            }
            catch (Exception ex) { PerfilLog.Error("ESTILO", "etiqueta " + nombre, ex); PerfilLog.Aviso("Estilo de etiqueta no disponible: " + nombre); return ObjectId.Null; }
        }

        private static ObjectId Componente(LabelStyle ls, Transaction tr, string nombre, LabelStyleComponentType tipo)
        {
            try
            {
                foreach (ObjectId id in ls.GetComponents(tipo))
                    if (((LabelStyleComponent)tr.GetObject(id, OpenMode.ForRead)).Name == nombre) return id;
            }
            catch { }
            return ObjectId.Null;
        }

        /// <summary>E.8-2: quita todos los componentes cuyo Name no sea <paramref name="conservar"/> (estilo ya abierto ForWrite).</summary>
        internal static void PurgarComponentes(LabelStyle ls, Transaction tr, string conservar)
        {
            foreach (LabelStyleComponentType t in Enum.GetValues(typeof(LabelStyleComponentType)))
            {
                try
                {
                    if (!ls.IsSupportedComponent(t)) continue;
                    var nombres = new List<string>();
                    foreach (ObjectId id in ls.GetComponents(t))
                        try { nombres.Add(((LabelStyleComponent)tr.GetObject(id, OpenMode.ForRead)).Name); } catch { }
                    foreach (string n in nombres)
                        if (n != conservar) try { ls.RemoveComponent(n); } catch (Exception ex) { PerfilLog.Log("ESTILO", "RemoveComponent " + n + ": " + ex.Message); }
                }
                catch { }
            }
        }

        /// <summary>E.9: "PDFCAD Perfil Profundidad{SufijoPl}" (Contents = solo tokens, alto 0.12"). Null si la colección está vacía (aviso).</summary>
        internal static ObjectId AsegurarProfundidad(Transaction tr, CivilDocument civDoc, EstilosPerfil est)
        {
            string nombre = "PDFCAD Perfil Profundidad" + (est.SufijoPl ?? "");
            try
            {
                var col = civDoc.Styles.LabelStyles.ProfileViewLabelStyles.DepthLabelStyles;
                if (col.Count == 0) { PerfilLog.Aviso("ESTILO", "Sin estilos de profundidad: no hay recubrimientos ni separaciones"); return ObjectId.Null; }
                ObjectId id = PerfilEstilos.Asegurar(col, nombre, tr, out _);
                var ls = (LabelStyle)tr.GetObject(id, OpenMode.ForWrite);
                double f = est.FactorPl;
                foreach (ObjectId cid in ls.GetComponents(LabelStyleComponentType.Text))
                {
                    var c = (LabelStyleTextComponent)tr.GetObject(cid, OpenMode.ForWrite);
                    string cont = ""; try { cont = c.Text.Contents.Value; } catch { }
                    PerfilLog.Log("ESTILO", "Profundidad Contents de fábrica: " + cont);
                    string solo = SoloTokens(cont);
                    if (solo.Length > 0) PerfilEstilos.Set(nombre, "Contents", () => c.Text.Contents.Value = solo);
                    else PerfilLog.Log("ESTILO", "Contents sin token");
                    PerfilEstilos.Set(nombre, "Height", () => c.Text.Height.Value = PerfilEstilos.Pl(0.12, f));
                    PerfilEstilos.Set(nombre, "Border", () => { c.Border.BackgroundMask.Value = true; c.Border.Gap.Value = PerfilEstilos.Pl(0.02, f); });
                }
                Lineas(ls, tr, nombre, false);
                PerfilEstilos.Set(nombre, "Label", () => { ls.Properties.Label.TextStyle.Value = PerfilEstilos.TEXTSTYLE; ls.Properties.Label.Layer.Value = PerfilEstilos.CAPA; });
                return id;
            }
            catch (Exception ex) { PerfilLog.Error("ESTILO", nombre, ex); return ObjectId.Null; }
        }

        private static void Lineas(LabelStyle ls, Transaction tr, string nombre, bool color7)
        {
            try
            {
                foreach (ObjectId lid in ls.GetComponents(LabelStyleComponentType.Line))
                {
                    var l = (LabelStyleLineComponent)tr.GetObject(lid, OpenMode.ForWrite);
                    PerfilEstilos.Set(nombre, "Linea", () => { l.Line.Lineweight.Value = LineWeight.LineWeight018; if (color7) l.Line.Color.Value = PerfilEstilos.Aci(7); });
                }
            }
            catch { }
        }

        /// <summary>E.9: "PDFCAD Perfil Limite{SufijoPl}" (textos ocultos, líneas 018 color 7) para las verticales de límite.</summary>
        internal static ObjectId AsegurarLimite(Transaction tr, CivilDocument civDoc, EstilosPerfil est)
        {
            string nombre = "PDFCAD Perfil Limite" + (est.SufijoPl ?? "");
            try
            {
                var col = civDoc.Styles.LabelStyles.ProfileViewLabelStyles.DepthLabelStyles;
                if (col.Count == 0) return ObjectId.Null;
                ObjectId id = PerfilEstilos.Asegurar(col, nombre, tr, out _);
                var ls = (LabelStyle)tr.GetObject(id, OpenMode.ForWrite);
                foreach (ObjectId cid in ls.GetComponents(LabelStyleComponentType.Text))
                {
                    var c = (LabelStyleTextComponent)tr.GetObject(cid, OpenMode.ForWrite);
                    PerfilEstilos.Set(nombre, "Texto oculto", () => c.General.Visible.Value = false);
                }
                Lineas(ls, tr, nombre, true);
                PerfilEstilos.Set(nombre, "Label", () => ls.Properties.Label.Layer.Value = PerfilEstilos.CAPA);
                return id;
            }
            catch (Exception ex) { PerfilLog.Error("ESTILO", nombre, ex); return ObjectId.Null; }
        }

        /// <summary>E.2/E.9: concatena solo los tokens &lt;[...]&gt; de un texto (regex &lt;\[[^\]]*\]&gt;); "" si no hay.</summary>
        internal static string SoloTokens(string contenido)
        {
            if (string.IsNullOrEmpty(contenido)) return "";
            var sb = new System.Text.StringBuilder();
            foreach (Match m in TOKEN.Matches(contenido)) sb.Append(m.Value);
            return sb.ToString();
        }

        /// <summary>E.10 (T1a): vuelca al log la configuración y los valores de fábrica (bases ≠ PDFCAD) y el FactorPl inicial con su origen.</summary>
        internal static void Diagnostico(Transaction tr, Database db, CivilDocument civDoc, double factorPl, string origenFactor)
        {
            void L(string m) { PerfilLog.Log("DIAG", m); }
            try { var u = civDoc.Settings.DrawingSettings.UnitZoneSettings; L($"DrawingScale={u.DrawingScale} DrawingUnits={u.DrawingUnits}"); } catch (Exception ex) { L("unidades: " + ex.Message); }
            try { var c = db.Cannoscale; L($"Cannoscale {c.Name} Scale={c.Scale} Paper={c.PaperUnits} Drawing={c.DrawingUnits} Ltscale={db.Ltscale}"); } catch (Exception ex) { L("cannoscale: " + ex.Message); }
            try
            {
                ObjectId b = PerfilEstilos.PrimeraBase(civDoc.Styles.ProfileViewStyles, tr);
                if (!b.IsNull)
                {
                    var p = (ProfileViewStyle)tr.GetObject(b, OpenMode.ForRead);
                    var m = p.BottomAxis.MajorTickStyle;
                    L($"PVS '{p.Name}': HScale={p.GraphStyle.CurrentHorizontalScale} VE={p.GraphStyle.VerticalExaggeration} tick h={m.TextHeight} size={m.Size} off=({m.OffsetX},{m.OffsetY}) rot={m.Rotation} just={m.Justification} txt={m.LabelText}");
                    var tl = p.LeftAxis.TitleStyle;
                    L($"  LeftAxis.Title h={tl.TextHeight} rot={tl.Rotation} off=({tl.OffsetX},{tl.OffsetY})");
                }
            }
            catch (Exception ex) { L("PVS: " + ex.Message); }
            try
            {
                var col = civDoc.Styles.LabelStyles.ProfileViewLabelStyles.StationElevationLabelStyles;
                ObjectId b = PerfilEstilos.PrimeraBase(col, tr);
                if (!b.IsNull)
                {
                    var ls = (LabelStyle)tr.GetObject(b, OpenMode.ForRead);
                    foreach (ObjectId cid in ls.GetComponents(LabelStyleComponentType.Text))
                    {
                        var c = (LabelStyleTextComponent)tr.GetObject(cid, OpenMode.ForRead);
                        L($"SEL '{ls.Name}': contents={c.Text.Contents.Value} h={c.Text.Height.Value} ang={c.Text.Angle.Value} att={c.Text.Attachment.Value} anchor={c.General.AnchorComponent.Value}/{c.General.AnchorLocation.Value}");
                        break;
                    }
                    var pr = ls.Properties;
                    L($"  leader flecha={pr.Leader.ArrowheadStyle.Value} tam={pr.Leader.ArrowheadSize.Value} forma={pr.Leader.Shape.Value}");
                    L($"  dragged {pr.DraggedStateComponents.DisplayType.Value} {pr.DraggedStateComponents.LeaderAttachment.Value} just={pr.DraggedStateComponents.LeaderJustification.Value}");
                }
            }
            catch (Exception ex) { L("SEL: " + ex.Message); }
            try
            {
                var col = civDoc.Styles.LabelStyles.ProfileViewLabelStyles.DepthLabelStyles;
                ObjectId b = PerfilEstilos.PrimeraBase(col, tr);
                if (!b.IsNull)
                    foreach (ObjectId cid in ((LabelStyle)tr.GetObject(b, OpenMode.ForRead)).GetComponents(LabelStyleComponentType.Text))
                    { L("Depth contents=" + ((LabelStyleTextComponent)tr.GetObject(cid, OpenMode.ForRead)).Text.Contents.Value); break; }
            }
            catch (Exception ex) { L("Depth: " + ex.Message); }
            L($"FactorPl inicial={factorPl:G6} ({origenFactor})");
        }
    }
}
